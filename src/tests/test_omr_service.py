from pathlib import Path

from src.services import omr_service


def test_run_omr_directory_preserves_output_directory(monkeypatch, tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()

    def fake_entry_point(root_dir, args):
        results_dir = Path(args["output_dir"]) / "Results"
        checked_dir = Path(args["output_dir"]) / "CheckedOMRs"
        results_dir.mkdir(parents=True)
        checked_dir.mkdir(parents=True)
        (results_dir / "Results_001.csv").write_text(
            "file_id,input_path,output_path,score\n"
            "sheet-1.png,input/sheet-1.png,output/CheckedOMRs/sheet-1.png,1\n",
            encoding="utf-8",
        )
        (checked_dir / "sheet-1.png").write_bytes(b"checked")

    monkeypatch.setattr(omr_service, "entry_point", fake_entry_point)

    result = omr_service.run_omr_directory(input_dir, output_dir)

    assert len(result.rows) == 1
    assert (output_dir / "Results" / "Results_001.csv").exists()
    assert (output_dir / "CheckedOMRs" / "sheet-1.png").exists()
