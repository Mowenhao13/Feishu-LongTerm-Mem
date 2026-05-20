// internal/llm/error_handling/recovery.go

package error_handling

import "time"

// Recovery 失败恢复机制
type Recovery struct {
	maxRetries    int
	maxTokens     int
	timeout       time.Duration
	humanFallback bool
}

type RecoveryStrategy struct {
	Strategy string // "retry" | "rollback" | "fallback" | "human"
}

func NewRecovery(maxRetries, maxTokens int, timeout time.Duration) *Recovery {
	return &Recovery{
		maxRetries: maxRetries,
		maxTokens:  maxTokens,
		timeout:    timeout,
	}
}

// Recover 执行恢复
func (r *Recovery) Recover(err error, checkpoint *Checkpoint) *RecoveryStrategy {
	// 1. 失败检测
	failureType := r.classifyFailure(err)

	// 2. 显性/隐性分类
	switch failureType {
	case "explicit":
		// 显性失败：直接重试
		return &RecoveryStrategy{Strategy: "retry"}
	case "implicit_loop":
		// 隐性失败：死循环
		return &RecoveryStrategy{Strategy: "rollback"}
	case "implicit_drift":
		// 隐性失败：方向偏离
		return &RecoveryStrategy{Strategy: "rollback"}
	case "implicit_overflow":
		// 隐性失败：上下文溢出
		return &RecoveryStrategy{Strategy: "fallback"}
	}

	// 3. 最终兜底
	return &RecoveryStrategy{Strategy: "human"}
}

// classifyFailure 分类失败类型
func (r *Recovery) classifyFailure(err error) string {
	if err == nil {
		return "none"
	}

	errStr := err.Error()

	// 检查显性失败
	if strings.Contains(errStr, "timeout") ||
		strings.Contains(errStr, "rate limit") ||
		strings.Contains(errStr, "429") ||
		strings.Contains(errStr, "5xx") {
		return "explicit"
	}

	// 检查隐性失败
	if strings.Contains(errStr, "loop") ||
		strings.Contains(errStr, "infinite") {
		return "implicit_loop"
	}

	if strings.Contains(errStr, "drift") ||
		strings.Contains(errStr, "off track") {
		return "implicit_drift"
	}

	if strings.Contains(errStr, "overflow") ||
		strings.Contains(errStr, "context") ||
		strings.Contains(errStr, "token limit") {
		return "implicit_overflow"
	}

	// 默认
	return "explicit"
}

// strings 包的简化引用
var strings = struct{ Contains func(string, string) bool }{
	Contains: func(s, substr string) bool {
		return len(s) >= len(substr) && (s == substr || len(substr) == 0 ||
			(len(s) > len(substr) && containsSubstring(s, substr)))
	},
}

func containsSubstring(s, substr string) bool {
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}
