package signal

import (
	"feishu-mem/internal/decision"
)

// AssembledContext 装配后的上下文包
type AssembledContext struct {
	Decisions      []*decision.DecisionNode // 相关决策
	AdapterResults map[AdapterType]any      // 各适配器查询结果
	CorrelationHints []CorrelationHint      // 关联提示
	TotalTokens    int                      // 消耗的 token 数
}

// CorrelationHint 关联提示
type CorrelationHint struct {
	Type        string  // DocDecisionLink | TaskDecisionProgress | MeetingDecisionLink | PersonDecisionLink
	Confidence  float64
	TargetSDR   string
	Description string
}

// ContextAssembler 上下文装配器
type ContextAssembler struct{}

// NewContextAssembler 创建上下文装配器
func NewContextAssembler() *ContextAssembler {
	return &ContextAssembler{}
}

// Assemble 在 token 预算内贪心装配上下文
func (a *ContextAssembler) Assemble(
	signal *StateChangeSignal,
	queryResults map[AdapterType]any,
	existingDecisions []*decision.DecisionNode,
	budget int,
) *AssembledContext {
	ctx := &AssembledContext{
		Decisions:      []*decision.DecisionNode{},
		AdapterResults: make(map[AdapterType]any),
		CorrelationHints: []CorrelationHint{},
		TotalTokens:    0,
	}

	// 添加现有决策
	for _, d := range existingDecisions {
		if ctx.TotalTokens < budget {
			ctx.Decisions = append(ctx.Decisions, d)
			ctx.TotalTokens += 100 // 估算
		}
	}

	// 添加查询结果
	for adapter, result := range queryResults {
		if ctx.TotalTokens < budget {
			ctx.AdapterResults[adapter] = result
			ctx.TotalTokens += 200 // 估算
		}
	}

	// 简单的关联提示
	for _, d := range existingDecisions {
		if ctx.TotalTokens < budget {
			ctx.CorrelationHints = append(ctx.CorrelationHints, CorrelationHint{
				Type:       "RelatesTo",
				Confidence: 0.5,
				TargetSDR:  d.SDRID,
				Description: "Potentially related decision",
			})
		}
	}

	return ctx
}

// FilterDecisionsByRelevance 根据相关性过滤决策
func (a *ContextAssembler) FilterDecisionsByRelevance(
	decisions []*decision.DecisionNode,
	signal *StateChangeSignal,
) []*decision.DecisionNode {
	// 简单的过滤实现
	var filtered []*decision.DecisionNode
	for _, d := range decisions {
		// 检查关键词匹配
		for _, kw := range signal.Context.Keywords {
			if contains(d.Title, kw) || contains(d.Decision, kw) {
				filtered = append(filtered, d)
				break
			}
		}
	}
	return filtered
}

func contains(s, substr string) bool {
	return len(s) >= len(substr) && indexOf(s, substr) >= 0
}

func indexOf(s, substr string) int {
	for i := 0; i <= len(s)-len(substr); i++ {
		match := true
		for j := 0; j < len(substr); j++ {
			if s[i+j] != substr[j] {
				match = false
				break
			}
		}
		if match {
			return i
		}
	}
	return -1
}
