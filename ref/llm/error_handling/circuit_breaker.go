// internal/llm/error_handling/circuit_breaker.go

package error_handling

import "time"

// CircuitBreaker 超时熔断器
type CircuitBreaker struct {
	timeout    time.Duration
	maxRetries int
	state      string // "closed" | "open" | "half-open"
	failCount  int
	lastFail   time.Time
}

func NewCircuitBreaker(timeout time.Duration, maxRetries int) *CircuitBreaker {
	return &CircuitBreaker{
		timeout:    timeout,
		maxRetries: maxRetries,
		state:      "closed",
	}
}

// Execute 执行操作（带熔断）
func (cb *CircuitBreaker) Execute(operation func() error) error {
	if cb.state == "open" {
		// 检查是否可以进入 half-open 状态
		if time.Since(cb.lastFail) > cb.timeout {
			cb.state = "half-open"
		} else {
			return nil // 熔断器打开，直接返回
		}
	}

	// 执行操作
	err := operation()
	if err != nil {
		cb.recordFailure()
		return err
	}
	cb.recordSuccess()
	return nil
}

func (cb *CircuitBreaker) recordFailure() {
	cb.failCount++
	cb.lastFail = time.Now()
	if cb.failCount >= cb.maxRetries {
		cb.state = "open"
	}
}

func (cb *CircuitBreaker) recordSuccess() {
	cb.failCount = 0
	cb.state = "closed"
}

// State 获取当前状态
func (cb *CircuitBreaker) State() string {
	return cb.state
}
