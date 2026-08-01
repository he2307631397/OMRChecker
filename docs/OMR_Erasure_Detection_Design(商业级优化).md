# 单选题多次填涂后擦除场景识别方案

## 1. 场景说明

答题卡存在一种特殊情况：

学生先填涂多个选项，之后擦除其中一个或多个，希望保留一个答案。

例如：

初始：

    A ●
    B ●
    C ●
    D ○

擦除后：

    A ●
    B △
    C △
    D ○

扫描后可能表现为：

    A mean=190
    B mean=225
    C mean=230
    D mean=248

该场景不同于普通弱填涂：

-   弱填涂：实际填了，但是颜色浅。
-   擦除修改：曾经填过，当前存在残留。

因此需要独立处理。

------------------------------------------------------------------------

# 2. 不应只使用候选排序

弱填方案：

    darkest candidate
    +
    gap
    +
    delta

适合恢复漏识别。

但擦除场景需要区分：

    真实填涂
    vs
    擦除残留

擦除后的区域可能仍然比空白深，但是没有完整填涂特征。

------------------------------------------------------------------------

# 3. 增加 Bubble Feature

每个选项增加更多特征：

``` java
BubbleFeature {

    double mean;

    double darkRatio;

    double centerDensity;

    double edgeDensity;

    double connectedRatio;
}
```

------------------------------------------------------------------------

# 4. 中心区域与边缘区域分析

完整填涂：

    +--------+
    | ██████ |
    | ██████ |
    | ██████ |
    +--------+

特点：

-   中心区域存在大量墨迹。
-   覆盖比较均匀。

擦除残留：

    +--------+
    | ░░░░░░ |
    |   ░    |
    |        |
    +--------+

特点：

-   中心区域恢复较干净。
-   边缘可能存在残留。

建议：

    FillScore =
    centerDensity - edgeDensity

------------------------------------------------------------------------

# 5. Bubble 状态分类

每个选项增加状态：

    EMPTY
    MARK
    WEAK_MARK
    ERASE_TRACE

例如：

    A -> MARK
    B -> ERASE_TRACE
    C -> ERASE_TRACE
    D -> EMPTY

最终：

    答案=A

    疑似擦除:
    B,C

------------------------------------------------------------------------

# 6. 单选冲突检测

正常单选：

    一个 MARK
    其它 EMPTY

风险：

    A MARK
    B WEAK_MARK
    C WEAK_MARK
    D EMPTY

不应直接输出。

进入：

    ambiguous_single_choice

输出：

-   推荐答案。
-   疑似擦除选项。
-   风险等级。

------------------------------------------------------------------------

# 7. 架构位置

擦除检测不属于弱填 fallback。

推荐：

    Normal OMR

          |
          +----------------+
          |                |
        正常结果        异常分析

                           |
                  +--------+---------+
                  |                  |
          Weak Fill Recovery   Erasure Detection
                  |                  |
           恢复漏识别          判断修改痕迹

------------------------------------------------------------------------

# 8. 第一阶段实现

## V1

增加：

    BubbleFeature

    mean
    darkRatio
    centerDensity
    edgeDensity

增加状态：

    EMPTY
    MARK
    WEAK_MARK
    ERASE_TRACE

增加单选冲突检测。

------------------------------------------------------------------------

## V2

增加：

    EraseScore =
    edgeDensity
    - centerDensity
    + residualArea

------------------------------------------------------------------------

## V3

增加机器学习模型：

输入：

    mean
    darkRatio
    centerDensity
    edgeDensity
    gap
    fieldType

输出：

    mark_probability
    erase_probability

------------------------------------------------------------------------

# 9. 与 Weak-fill 的关系

两个问题分开：

  问题               方案
  ------------------ --------------------
  填了但没识别出来   Weak Fill Recovery
  填过多个又擦除     Erasure Detection

最终：

    Adaptive OMR

     + Weak Fill Recognition
     + Multiple Mark Analysis
     + Erasure Detection
     + Manual Review

------------------------------------------------------------------------

# 10. 结论

多次填涂后擦除属于高风险 OMR 场景。

最佳方案：

    识别填涂状态
    +
    判断擦除痕迹
    +
    检测单选冲突
    +
    保留审计信息

该能力应作为答题卡识别引擎独立模块设计。
