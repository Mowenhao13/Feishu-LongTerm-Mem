// internal/llm/error_handling/checker.go

package error_handling

import "time"

// Checkpoint 检查点
type Checkpoint struct {
	StepID    string
	State     map[string]any
	Timestamp time.Time
}

// CheckpointManager 检查点管理器
type CheckpointManager struct {
	checkpoints map[string]*Checkpoint
}

func NewCheckpointManager() *CheckpointManager {
	return &CheckpointManager{
		checkpoints: make(map[string]*Checkpoint),
	}
}

// Save 保存检查点
func (m *CheckpointManager) Save(stepID string, state map[string]any) {
	m.checkpoints[stepID] = &Checkpoint{
		StepID:    stepID,
		State:     state,
		Timestamp: time.Now(),
	}
}

// Load 加载检查点
func (m *CheckpointManager) Load(stepID string) *Checkpoint {
	return m.checkpoints[stepID]
}

// Rollback 回滚到检查点
func (m *CheckpointManager) Rollback(stepID string) error {
	checkpoint := m.Load(stepID)
	if checkpoint == nil {
		return nil // 没有检查点，静默返回
	}
	// 恢复状态 - 这里的具体实现取决于使用场景
	return nil
}

// ListCheckpoints 列出所有检查点
func (m *CheckpointManager) ListCheckpoints() []*Checkpoint {
	checkpoints := make([]*Checkpoint, 0, len(m.checkpoints))
	for _, cp := range m.checkpoints {
		checkpoints = append(checkpoints, cp)
	}
	return checkpoints
}

// Clear 清除所有检查点
func (m *CheckpointManager) Clear() {
	m.checkpoints = make(map[string]*Checkpoint)
}
