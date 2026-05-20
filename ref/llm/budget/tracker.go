// internal/llm/budget/tracker.go

package budget

// TokenBudget 各层预算限制
// 对齐 docs/agent 集成设计价值观.md
type TokenBudget struct {
	SearchTool    int // 搜索工具 ≤ 2w字符
	FileRead      int // 文件读取特殊处理
	TotalPerAgent int // 单个Agent预算
	MaxTotal      int // 全局预算上限
}

// DefaultBudget 默认预算
func DefaultBudget() TokenBudget {
	return TokenBudget{
		SearchTool:    20000, // 2w字符
		FileRead:      10000, // 特殊处理
		TotalPerAgent: 8000,  // 单个Agent
		MaxTotal:      50000, // 全局上限
	}
}

// BudgetTracker 预算追踪器
type BudgetTracker struct {
	used    int
	limits  TokenBudget
	history []string
}

func NewBudgetTracker(limits TokenBudget) *BudgetTracker {
	return &BudgetTracker{
		limits: limits,
	}
}

// CanUse 检查是否有足够的预算
func (bt *BudgetTracker) CanUse(tool string, estimatedTokens int) bool {
	return bt.used+estimatedTokens <= bt.limits.MaxTotal
}

// Consume 消耗预算
func (bt *BudgetTracker) Consume(tool string, tokens int) {
	bt.used += tokens
	bt.history = append(bt.history, tool)
}

// GetUsed 获取已使用预算
func (bt *BudgetTracker) GetUsed() int {
	return bt.used
}

// GetRemaining 获取剩余预算
func (bt *BudgetTracker) GetRemaining() int {
	return bt.limits.MaxTotal - bt.used
}

// GetLimits 获取预算限制
func (bt *BudgetTracker) GetLimits() TokenBudget {
	return bt.limits
}
