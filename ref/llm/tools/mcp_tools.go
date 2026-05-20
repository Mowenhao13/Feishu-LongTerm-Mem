// internal/llm/tools/mcp_tools.go

package tools

// ToolRegistry 工具注册表（两级加载）
type ToolRegistry struct {
	// 第一级：轻量描述（searchHint）
	Hints map[string]*ToolHint

	// 第二级：完整定义（按需加载）
	FullTools map[string]*ToolDefinition
}

// ToolHint 轻量描述
type ToolHint struct {
	Name        string
	SearchHint  string // 搜索关键词
	Description string // 一句话描述
}

// ToolDefinition 完整定义
type ToolDefinition struct {
	Name         string
	Description  string
	InputSchema  map[string]any
	OutputBudget int // Token 预算
	Handler      func(input any) (any, error)
}

// NewToolRegistry 创建工具注册表
func NewToolRegistry() *ToolRegistry {
	r := &ToolRegistry{
		Hints:     make(map[string]*ToolHint),
		FullTools: make(map[string]*ToolDefinition),
	}
	r.registerAllTools()
	return r
}

// registerAllTools 注册所有工具
func (r *ToolRegistry) registerAllTools() {
	// MCP 工具
	r.RegisterMCPTools()

	// 专用工具
	r.RegisterSearchTool()
	r.RegisterParseTool()
}

// RegisterMCPTools 注册 MCP 工具（两级加载）
func (r *ToolRegistry) RegisterMCPTools() {
	// 第一级：轻量描述
	r.Hints["mcp.search"] = &ToolHint{
		Name:        "mcp.search",
		SearchHint:  "search, 搜索, 决策",
		Description: "搜索记忆系统中的决策记录",
	}

	r.Hints["mcp.topic"] = &ToolHint{
		Name:        "mcp.topic",
		SearchHint:  "topic, 议题, 分类",
		Description: "查看某议题的决策图谱",
	}

	r.Hints["mcp.decision"] = &ToolHint{
		Name:        "mcp.decision",
		SearchHint:  "decision, 决策, 详情",
		Description: "查看某决策详情",
	}

	// 第二级：完整定义（按需加载）
	// 暂时省略
}

// RegisterSearchTool 注册搜索工具
func (r *ToolRegistry) RegisterSearchTool() {
	r.Hints["search"] = &ToolHint{
		Name:        "search",
		SearchHint:  "search, 查找, 搜索",
		Description: "搜索决策记录（专用工具，预算 2w 字符）",
	}

	r.FullTools["search"] = &ToolDefinition{
		Name:         "search",
		Description:  "搜索决策记录",
		OutputBudget: 20000, // ≤ 2w字符
	}
}

// RegisterParseTool 注册解析工具
func (r *ToolRegistry) RegisterParseTool() {
	r.Hints["parse"] = &ToolHint{
		Name:        "parse",
		SearchHint:  "parse, 解析, json",
		Description: "解析 LLM 输出的 JSON 内容",
	}

	r.FullTools["parse"] = &ToolDefinition{
		Name:         "parse",
		Description:  "JSON 解析工具",
		OutputBudget: 1000,
	}
}

// GetToolHint 获取工具提示
func (r *ToolRegistry) GetToolHint(name string) (*ToolHint, bool) {
	hint, ok := r.Hints[name]
	return hint, ok
}

// GetToolDefinition 获取工具定义
func (r *ToolRegistry) GetToolDefinition(name string) (*ToolDefinition, bool) {
	def, ok := r.FullTools[name]
	return def, ok
}

// SearchTools 搜索工具（两级加载搜索）
func (r *ToolRegistry) SearchTools(query string) []*ToolHint {
	var results []*ToolHint
	for _, hint := range r.Hints {
		if containsSubstring(hint.Name, query) ||
			containsSubstring(hint.SearchHint, query) ||
			containsSubstring(hint.Description, query) {
			results = append(results, hint)
		}
	}
	return results
}

func containsSubstring(s, substr string) bool {
	if len(substr) == 0 {
		return true
	}
	if len(s) < len(substr) {
		return false
	}
	for i := 0; i <= len(s)-len(substr); i++ {
		if s[i:i+len(substr)] == substr {
			return true
		}
	}
	return false
}

// GetAllHints 获取所有工具提示
func (r *ToolRegistry) GetAllHints() []*ToolHint {
	var hints []*ToolHint
	for _, hint := range r.Hints {
		hints = append(hints, hint)
	}
	return hints
}
