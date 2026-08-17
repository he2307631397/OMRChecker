"""
Image based feature alignment
Credits: https://www.learnopencv.com/image-alignment-feature-based-using-opencv-c-python/
"""
import cv2
import numpy as np

from src.logger import logger
from src.processors.interfaces.ImagePreprocessor import ImagePreprocessor
from src.utils.image import ImageUtils
from src.utils.interaction import InteractionUtils
from src.constants.image_processing import (
    DEFAULT_MAX_FEATURES,
    DEFAULT_GOOD_MATCH_PERCENT
)


class FeatureBasedAlignment(ImagePreprocessor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        options = self.options
        config = self.tuning_config

        # process reference image
        self.ref_path = self.relative_dir.joinpath(options["reference"])
        ref_img = cv2.imdecode(
            np.frombuffer(self.ref_path.read_bytes(), dtype=np.uint8),
            cv2.IMREAD_GRAYSCALE,
        )
        self.ref_img = ImageUtils.resize_util(
            ref_img,
            config.dimensions.processing_width,
            config.dimensions.processing_height,
        )
        # get options with defaults
        self.max_features = int(options.get("maxFeatures", DEFAULT_MAX_FEATURES))
        self.good_match_percent = options.get("goodMatchPercent", DEFAULT_GOOD_MATCH_PERCENT)
        self.transform_2_d = options.get("2d", False)
        # Extract keypoints and description of source image
        self.orb = cv2.ORB_create(self.max_features)
        self.to_keypoints, self.to_descriptors = self.orb.detectAndCompute(
            self.ref_img, None
        )
        if self.to_descriptors is None or len(self.to_keypoints) == 0:
            logger.warning(f"FeatureBasedAlignment reference has no ORB descriptors: {self.ref_path}")

    def __str__(self):
        return self.ref_path.name

    def exclude_files(self):
        return [self.ref_path]

    def apply_filter(self, image, _file_path):
        config = self.tuning_config
        # Convert images to grayscale
        # im1Gray = cv2.cvtColor(im1, cv2.COLOR_BGR2GRAY)
        # im2Gray = cv2.cvtColor(im2, cv2.COLOR_BGR2GRAY)

        image = cv2.normalize(image, 0, 255, norm_type=cv2.NORM_MINMAX)

        # Detect ORB features and compute descriptors.
        from_keypoints, from_descriptors = self.orb.detectAndCompute(image, None)

        if from_descriptors is None or self.to_descriptors is None:
            logger.warning(
                f"Skipping FeatureBasedAlignment for '{_file_path}': insufficient ORB descriptors "
                f"(source={0 if from_descriptors is None else len(from_keypoints)}, "
                f"reference={0 if self.to_descriptors is None else len(self.to_keypoints)})"
            )
            return image

        # Match features.
        matcher = cv2.DescriptorMatcher_create(
            cv2.DESCRIPTOR_MATCHER_BRUTEFORCE_HAMMING
        )

        # create BFMatcher object (alternate matcher)
        # matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)

        matches = np.array(matcher.match(from_descriptors, self.to_descriptors, None))

        # Sort matches by score
        matches = sorted(matches, key=lambda x: x.distance, reverse=False)

        # Remove not so good matches
        num_good_matches = int(len(matches) * self.good_match_percent)
        matches = matches[:num_good_matches]

        min_required_matches = 3 if self.transform_2_d else 4
        if len(matches) < min_required_matches:
            logger.warning(
                f"Skipping FeatureBasedAlignment for '{_file_path}': only {len(matches)} good matches, "
                f"requires at least {min_required_matches}"
            )
            return image

        # Draw top matches
        if config.outputs.show_image_level > 2:
            im_matches = cv2.drawMatches(
                image, from_keypoints, self.ref_img, self.to_keypoints, matches, None
            )
            InteractionUtils.show("Aligning", im_matches, resize=True, config=config)

        # Extract location of good matches
        points1 = np.zeros((len(matches), 2), dtype=np.float32)
        points2 = np.zeros((len(matches), 2), dtype=np.float32)

        for i, match in enumerate(matches):
            points1[i, :] = from_keypoints[match.queryIdx].pt
            points2[i, :] = self.to_keypoints[match.trainIdx].pt

        # Find homography
        height, width = self.ref_img.shape
        if self.transform_2_d:
            try:
                m, _inliers = cv2.estimateAffine2D(points1, points2)
            except cv2.error as exc:
                logger.warning(f"Skipping FeatureBasedAlignment for '{_file_path}': affine transform estimation errored: {exc}")
                return image
            if m is None:
                logger.warning(f"Skipping FeatureBasedAlignment for '{_file_path}': affine transform estimation failed")
                return image
            return cv2.warpAffine(image, m, (width, height))

        # Use homography
        try:
            h, _mask = cv2.findHomography(points1, points2, cv2.RANSAC)
        except cv2.error as exc:
            logger.warning(f"Skipping FeatureBasedAlignment for '{_file_path}': homography estimation errored: {exc}")
            return image
        if h is None:
            logger.warning(f"Skipping FeatureBasedAlignment for '{_file_path}': homography estimation failed")
            return image
        return cv2.warpPerspective(image, h, (width, height))
