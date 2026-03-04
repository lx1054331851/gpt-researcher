from gpt_researcher.actions.report_generation import evaluate_goal_alignment


def test_goal_alignment_passes_when_conclusion_addresses_object_and_timepoint():
    query = "为 Patagonia 制定 2027 面料升级建议"
    report = """
# 报告
## 关键发现
- 2026 年再生尼龙成本下降 12% ([S1](https://example.com/s1))

## 结论
针对 Patagonia 在 2027 年的面料升级，建议优先采用再生尼龙与防水膜双路线，
并在 2027Q2 前完成供应商验证。
"""
    ok, issues = evaluate_goal_alignment(report, query)
    assert ok is True
    assert not issues


def test_goal_alignment_flags_methodology_only_output():
    query = "Nike 2027 产品策略建议"
    report = """
# Strategy Note
## Framework
This report proposes a generic methodology and framework for future work.
The methodology includes high-level process and framework checkpoints.

## Conclusion
Follow the framework and methodology above.
"""
    ok, issues = evaluate_goal_alignment(report, query)
    assert ok is False
    assert "methodology_only_without_facts" in issues


def test_goal_alignment_flags_single_dimension_bias():
    query = "2027 企业AI平台建设决策建议"
    report = """
# 报告
## 技术架构综述
平台采用统一模型编排架构，重点讨论模型层和推理框架。

## 模型性能与技术细节
对比不同模型参数规模、推理吞吐和延迟指标，主要围绕模型技术路线展开。

## 工程实现细节
讨论部署拓扑、模型容器化、缓存优化和推理加速实现。

## 结论
建议继续优化模型架构与推理性能，聚焦技术路线迭代。
"""
    ok, issues = evaluate_goal_alignment(report, query)
    assert ok is False
    assert "single_dimension_bias" in issues
