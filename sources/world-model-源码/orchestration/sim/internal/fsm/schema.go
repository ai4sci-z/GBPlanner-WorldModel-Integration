package fsm

const SchemaVersion = "navlab.fsm.v1"

type Summary struct {
	SchemaVersion     string          `json:"schema_version"`
	FSMName           string          `json:"fsm_name"`
	ParentFSM         *ParentRef      `json:"parent_fsm,omitempty"`
	Scope             string          `json:"scope"`
	TaskID            string          `json:"task_id"`
	RunID             string          `json:"run_id"`
	State             string          `json:"state"`
	Mode              string          `json:"mode"`
	OK                bool            `json:"ok"`
	Blocked           bool            `json:"blocked"`
	States            []State         `json:"states"`
	Triggers          []Trigger       `json:"triggers"`
	Transitions       []Transition    `json:"transitions"`
	Guards            []Guard         `json:"guards,omitempty"`
	Evidence          map[string]any  `json:"evidence,omitempty"`
	ReasonCodes       []string        `json:"reason_codes,omitempty"`
	Blockers          []Blocker       `json:"blockers,omitempty"`
	SubFSMs           []ArtifactRef   `json:"sub_fsms,omitempty"`
	ArtifactPath      string          `json:"artifact_path,omitempty"`
	FailedState       string          `json:"failed_state,omitempty"`
	FailedTrigger     string          `json:"failed_trigger,omitempty"`
	FailureReasonCode string          `json:"failure_reason_code,omitempty"`
	Recoverable       *bool           `json:"recoverable,omitempty"`
	DebugArtifacts    []DebugArtifact `json:"debug_artifacts,omitempty"`
	CreatedAt         string          `json:"created_at"`
}

type ParentRef struct {
	FSMName      string `json:"fsm_name"`
	Scope        string `json:"scope"`
	ArtifactPath string `json:"artifact_path,omitempty"`
}

type ArtifactRef struct {
	FSMName           string `json:"fsm_name"`
	Scope             string `json:"scope"`
	ArtifactPath      string `json:"artifact_path"`
	State             string `json:"state"`
	OK                bool   `json:"ok"`
	Blocked           bool   `json:"blocked"`
	FailureReasonCode string `json:"failure_reason_code,omitempty"`
}

type DebugArtifact struct {
	Type string `json:"type"`
	Path string `json:"path"`
}

type State struct {
	State       string `json:"state"`
	Terminal    bool   `json:"terminal,omitempty"`
	Failure     bool   `json:"failure,omitempty"`
	Description string `json:"description,omitempty"`
}

type Trigger struct {
	Trigger     string `json:"trigger"`
	Description string `json:"description,omitempty"`
}

type Transition struct {
	FromState    string         `json:"from_state"`
	ToState      string         `json:"to_state"`
	Trigger      string         `json:"trigger"`
	At           string         `json:"at,omitempty"`
	OK           bool           `json:"ok"`
	ReasonCode   string         `json:"reason_code,omitempty"`
	Evidence     map[string]any `json:"evidence,omitempty"`
	GuardResults []Guard        `json:"guard_results,omitempty"`
}

type Guard struct {
	Name       string         `json:"name"`
	OK         bool           `json:"ok"`
	Required   bool           `json:"required"`
	ReasonCode string         `json:"reason_code,omitempty"`
	Evidence   map[string]any `json:"evidence,omitempty"`
}

type Blocker struct {
	Code    string `json:"code"`
	Message string `json:"message"`
	Source  string `json:"source,omitempty"`
}
