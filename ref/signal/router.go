package signal

// ActivationMatrix 8×3×8 权重矩阵
type ActivationMatrix struct {
	weights map[AdapterType]map[SignalStrength]map[AdapterType]float64
}

// NewActivationMatrix 创建激活矩阵
func NewActivationMatrix() *ActivationMatrix {
	m := &ActivationMatrix{
		weights: make(map[AdapterType]map[SignalStrength]map[AdapterType]float64),
	}

	// 初始化权重矩阵
	adapters := []AdapterType{
		AdapterIM, AdapterVC, AdapterDocs, AdapterCalendar,
		AdapterTask, AdapterOKR, AdapterContact, AdapterWiki,
	}
	strengths := []SignalStrength{StrengthStrong, StrengthMedium, StrengthWeak}

	for _, src := range adapters {
		m.weights[src] = make(map[SignalStrength]map[AdapterType]float64)
		for _, strength := range strengths {
			m.weights[src][strength] = make(map[AdapterType]float64)
			for _, dst := range adapters {
				m.weights[src][strength][dst] = m.getDefaultWeight(src, dst, strength)
			}
		}
	}

	return m
}

func (m *ActivationMatrix) getDefaultWeight(src, dst AdapterType, strength SignalStrength) float64 {
	base := 0.0
	switch strength {
	case StrengthStrong:
		base = 0.8
	case StrengthMedium:
		base = 0.5
	case StrengthWeak:
		base = 0.2
	}

	// 相关的适配器权重更高
	relatedPairs := map[[2]AdapterType]float64{
		{AdapterIM, AdapterVC}:       0.3,
		{AdapterVC, AdapterMinutes}:  0.3,
		{AdapterDocs, AdapterWiki}:   0.2,
		{AdapterTask, AdapterOKR}:    0.2,
		{AdapterCalendar, AdapterVC}: 0.2,
	}

	if delta, ok := relatedPairs[[2]AdapterType{src, dst}]; ok {
		base += delta
	}

	if base > 1.0 {
		base = 1.0
	}
	return base
}

// ActivationPriority 激活优先级
type ActivationPriority int

const (
	PrioritySkip ActivationPriority = iota // weight < 0.1
	PriorityMay                            // 0.1-0.4
	PriorityShould                         // 0.4-0.7
	PriorityMust                           // >= 0.7
)

// ActivationTarget 激活目标
type ActivationTarget struct {
	Adapter  AdapterType
	Weight   float64
	Priority ActivationPriority
}

// ContextQuery 上下文查询
type ContextQuery struct {
	QueryID       string
	TargetAdapter AdapterType
	TokenBudget   int
	Priority      int
	Purpose       string
}

// ContextQueryPlan 查询计划
type ContextQueryPlan struct {
	SignalID         string
	TotalTokenBudget int
	Queries          []ContextQuery
}

// ActivationRouter 激活路由器
type ActivationRouter struct {
	matrix *ActivationMatrix
}

// NewActivationRouter 创建激活路由器
func NewActivationRouter() *ActivationRouter {
	return &ActivationRouter{
		matrix: NewActivationMatrix(),
	}
}

// Route 根据信号决定需要查询哪些适配器
func (r *ActivationRouter) Route(signal *StateChangeSignal) *ContextQueryPlan {
	plan := &ContextQueryPlan{
		SignalID:         signal.SignalID,
		TotalTokenBudget: 8000,
		Queries:          []ContextQuery{},
	}

	adapters := []AdapterType{
		AdapterIM, AdapterVC, AdapterDocs, AdapterCalendar,
		AdapterTask, AdapterOKR, AdapterContact, AdapterWiki,
	}

	priorityOrder := 0
	for _, adapter := range adapters {
		if adapter == signal.Adapter {
			continue
		}

		weight := r.matrix.weights[signal.Adapter][signal.Strength][adapter]
		priority := r.getPriority(weight)

		if priority == PrioritySkip {
			continue
		}

		plan.Queries = append(plan.Queries, ContextQuery{
			QueryID:       "query-" + string(adapter),
			TargetAdapter: adapter,
			TokenBudget:   r.getTokenBudget(priority),
			Priority:      priorityOrder,
			Purpose:       "context-gathering",
		})
		priorityOrder++
	}

	return plan
}

func (r *ActivationRouter) getPriority(weight float64) ActivationPriority {
	switch {
	case weight >= 0.7:
		return PriorityMust
	case weight >= 0.4:
		return PriorityShould
	case weight >= 0.1:
		return PriorityMay
	default:
		return PrioritySkip
	}
}

func (r *ActivationRouter) getTokenBudget(priority ActivationPriority) int {
	switch priority {
	case PriorityMust:
		return 2000
	case PriorityShould:
		return 1000
	case PriorityMay:
		return 500
	default:
		return 0
	}
}

// AdapterMinutes 临时定义
const AdapterMinutes AdapterType = "Minutes"
