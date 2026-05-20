package larkadapter

import (
	"encoding/json"
	"fmt"
	"time"
)

// ContactExtractor 通讯录提取器
type ContactExtractor struct {
	config *Config
	cli    *LarkCLI
}

// NewContactExtractor 创建通讯录提取器
func NewContactExtractor(cfg *Config) *ContactExtractor {
	return &ContactExtractor{
		config: cfg,
		cli:    NewLarkCLI(),
	}
}

// Name 实现 Extractor 接口
func (e *ContactExtractor) Name() string {
	return "lark_contact"
}

// Detect 检测通讯录/人员变化
// 通讯录变化频率低，通过检测用户信息变更来判断
func (e *ContactExtractor) Detect(lastCheck time.Time) (*DetectResult, error) {
	var changes []Change
	cutoff := lastCheck.Unix()

	// 如果是首次检测，不报告变化（通讯录基线数据大）
	if lastCheck.IsZero() {
		result := &DetectResult{
			Source:     e.Name(),
			HasChanges: false,
			DetectedAt: time.Now(),
			LastCheck:  lastCheck,
		}
		_ = SaveDetectResult(result)
		return result, nil
	}

	// 尝试获取用户信息并分析变化
	output, err := e.cli.RunCommand("contact", "+search-user", "--query", "")
	if err == nil {
		changes = e.parseContactChanges(output, cutoff)
	}

	result := &DetectResult{
		Source:     e.Name(),
		HasChanges: len(changes) > 0,
		DetectedAt: time.Now(),
		LastCheck:  lastCheck,
		Changes:    changes,
	}

	_ = SaveDetectResult(result)
	return result, nil
}

// parseContactChanges 解析通讯录变化
func (e *ContactExtractor) parseContactChanges(output []byte, cutoff int64) []Change {
	var changes []Change

	var result []any
	if err := json.Unmarshal(output, &result); err != nil {
		var single any
		if err := json.Unmarshal(output, &single); err != nil {
			return changes
		}
		result = []any{single}
	}

	for _, item := range result {
		itemMap, ok := item.(map[string]any)
		if !ok {
			continue
		}
		data, ok := itemMap["data"].(map[string]any)
		if !ok {
			continue
		}
		users, ok := data["users"].([]any)
		if !ok {
			items, ok := data["items"].([]any)
			if ok {
				users = items
			} else {
				continue
			}
		}

		for _, u := range users {
			userMap, ok := u.(map[string]any)
			if !ok {
				continue
			}

			userID, _ := userMap["user_id"].(string)
			name, _ := userMap["name"].(string)
			enName, _ := userMap["en_name"].(string)

			if userID == "" {
				continue
			}

			displayName := name
			if displayName == "" {
				displayName = enName
			}

			// 检查用户状态
			status, _ := userMap["status"].(map[string]any)
			if isFrozen, ok := status["is_frozen"].(bool); ok && isFrozen {
				changes = append(changes, Change{
					Type:       "contact_user_frozen",
					EntityType: "contact",
					EntityID:   userID,
					Summary:    fmt.Sprintf("用户已冻结: %s", displayName),
				})
			}

			if isResigned, ok := status["is_resigned"].(bool); ok && isResigned {
				changes = append(changes, Change{
					Type:       "contact_user_resigned",
					EntityType: "contact",
					EntityID:   userID,
					Summary:    fmt.Sprintf("用户已离职: %s", displayName),
				})
			}

			// 检查是否有更新时间
			var userTs int64
			if updateTime, ok := userMap["update_time"].(string); ok {
				userTs = parseMessageTime(updateTime)
				if userTs > cutoff {
					changes = append(changes, Change{
						Type:       "contact_user_updated",
						EntityType: "contact",
						EntityID:   userID,
						Summary:    fmt.Sprintf("用户信息更新: %s", displayName),
						Timestamp:  userTs,
					})
				}
			}

			// 检查部门变更
			if departments, ok := userMap["departments"].([]any); ok && len(departments) > 0 {
				changes = append(changes, Change{
					Type:       "contact_department_changed",
					EntityType: "contact",
					EntityID:   userID,
					Summary:    fmt.Sprintf("用户部门可能变更: %s", displayName),
					Timestamp:  userTs,
				})
			}
		}
	}

	return changes
}

// Extract 提取联系人信息用于决策关联
func (e *ContactExtractor) Extract() error {
	rawData := make(map[string]any)

	if users, err := e.searchUsers(); err == nil {
		rawData["users"] = users
	}

	formatted := map[string]any{
		"extracted": true,
	}

	result := &ExtractionResult{
		Source:      e.Name(),
		ExtractedAt: time.Now(),
		RawData:     rawData,
		Formatted:   formatted,
	}

	if err := SaveToJSON(e.Name(), result); err != nil {
		return fmt.Errorf("save result failed: %w", err)
	}

	return nil
}

func (e *ContactExtractor) searchUsers() ([]any, error) {
	output, err := e.cli.RunCommand("contact", "+search-user", "--query", "")
	if err != nil {
		return nil, err
	}

	var result []any
	if err := json.Unmarshal(output, &result); err != nil {
		var single any
		if err := json.Unmarshal(output, &single); err != nil {
			return nil, err
		}
		result = []any{single}
	}
	return result, nil
}
