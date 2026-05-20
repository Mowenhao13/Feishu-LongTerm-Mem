package larkadapter

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
	"strings"
	"time"
)

// DefaultTimeout lark-cli 默认超时
const DefaultTimeout = 30 * time.Second

// LarkCLI lark-cli 调用封装
type LarkCLI struct {
	Timeout time.Duration
}

// NewLarkCLI 创建 lark-cli 封装
func NewLarkCLI() *LarkCLI {
	return &LarkCLI{Timeout: DefaultTimeout}
}

// RunCommand 运行 lark-cli 命令（带超时）
func (l *LarkCLI) RunCommand(args ...string) ([]byte, error) {
	ctx, cancel := context.WithTimeout(context.Background(), l.Timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, "lark-cli", args...)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return nil, fmt.Errorf("lark-cli %s timed out after %v", strings.Join(args, " "), l.Timeout)
		}
		return nil, fmt.Errorf("lark-cli %s failed: %w, stderr: %s", strings.Join(args, " "), err, stderr.String())
	}

	return stdout.Bytes(), nil
}

// RunCommandJSON 运行命令并解析 JSON 结果
func (l *LarkCLI) RunCommandJSON(result any, args ...string) error {
	output, err := l.RunCommand(args...)
	if err != nil {
		return err
	}
	return json.Unmarshal(output, result)
}
