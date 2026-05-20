// internal/llm/budget/cost_estimator.go

package budget

// CostEstimator 成本估算器
type CostEstimator struct {
	// 不同工具的成本估算
	toolCosts map[string]int
}

func NewCostEstimator() *CostEstimator {
	return &CostEstimator{
		toolCosts: map[string]int{
			"mcp.search":    500,
			"mcp.topic":     1000,
			"mcp.decision":  300,
			"mcp.timeline":  600,
			"mcp.conflict":  400,
			"mcp.signal":    300,
			"llm.call":      2000,
		},
	}
}

// Estimate 估算成本
func (ce *CostEstimator) Estimate(tool string) int {
	if cost, ok := ce.toolCosts[tool]; ok {
		return cost
	}
	return 0
}

// RegisterCost 注册工具成本
func (ce *CostEstimator) RegisterCost(tool string, cost int) {
	ce.toolCosts[tool] = cost
}
