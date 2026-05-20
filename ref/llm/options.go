// internal/llm/options.go

package llm

import "time"

// CallOptions 调用选项
type CallOptions struct {
	Timeout     time.Duration
	MaxRetries  int
	Temperature float64
	MaxTokens   int
	Budget      interface{}
}

// DefaultCallOptions 默认调用选项
func DefaultCallOptions() *CallOptions {
	return &CallOptions{
		Timeout:     30 * time.Second,
		MaxRetries:  3,
		Temperature: 0.3,
		MaxTokens:   2000,
	}
}

// WithTimeout 设置超时
func WithTimeout(timeout time.Duration) func(*CallOptions) {
	return func(opts *CallOptions) {
		opts.Timeout = timeout
	}
}

// WithMaxRetries 设置最大重试次数
func WithMaxRetries(retries int) func(*CallOptions) {
	return func(opts *CallOptions) {
		opts.MaxRetries = retries
	}
}

// WithTemperature 设置温度
func WithTemperature(temp float64) func(*CallOptions) {
	return func(opts *CallOptions) {
		opts.Temperature = temp
	}
}

// WithBudget 设置预算
func WithBudget(budget interface{}) func(*CallOptions) {
	return func(opts *CallOptions) {
		opts.Budget = budget
	}
}

// ApplyOptions 应用选项
func ApplyOptions(base *CallOptions, options ...func(*CallOptions)) *CallOptions {
	for _, opt := range options {
		opt(base)
	}
	return base
}
