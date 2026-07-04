package fsm

import (
	"context"
	"sort"
	"time"

	"github.com/qmuntal/stateless"
)

type Rule struct {
	From    string
	Trigger string
	To      string
}

type Recorder struct {
	machine *stateless.StateMachine
	summary Summary
}

func NewRecorder(fsmName string, scope string, taskID string, runID string, mode string, initialState string, states []State, triggers []Trigger, rules []Rule) *Recorder {
	recorder := &Recorder{
		machine: stateless.NewStateMachine(initialState),
		summary: Summary{
			SchemaVersion: SchemaVersion,
			FSMName:       fsmName,
			Scope:         scope,
			TaskID:        taskID,
			RunID:         runID,
			State:         initialState,
			Mode:          mode,
			States:        append([]State(nil), states...),
			Triggers:      append([]Trigger(nil), triggers...),
			Transitions:   []Transition{},
			Evidence:      map[string]any{},
			CreatedAt:     time.Now().UTC().Format(time.RFC3339Nano),
		},
	}
	for _, rule := range rules {
		recorder.machine.Configure(rule.From).Permit(rule.Trigger, rule.To)
	}
	return recorder
}

func (recorder *Recorder) SetParent(parent ParentRef) {
	recorder.summary.ParentFSM = &parent
}

func (recorder *Recorder) SetEvidence(evidence map[string]any) {
	recorder.summary.Evidence = cloneMap(evidence)
}

func (recorder *Recorder) SetArtifactPath(path string) {
	recorder.summary.ArtifactPath = path
}

func (recorder *Recorder) SetDebugArtifacts(artifacts []DebugArtifact) {
	recorder.summary.DebugArtifacts = append([]DebugArtifact(nil), artifacts...)
}

func (recorder *Recorder) Fire(trigger string, at string, ok bool, reasonCode string, evidence map[string]any, guards []Guard) error {
	before := recorder.summary.State
	if err := recorder.machine.FireCtx(context.Background(), trigger); err != nil {
		return err
	}
	after, err := recorder.machine.State(context.Background())
	if err != nil {
		return err
	}
	toState := after.(string)
	recorder.summary.State = toState
	recorder.summary.Transitions = append(recorder.summary.Transitions, Transition{
		FromState:    before,
		ToState:      toState,
		Trigger:      trigger,
		At:           at,
		OK:           ok,
		ReasonCode:   reasonCode,
		Evidence:     cloneMap(evidence),
		GuardResults: append([]Guard(nil), guards...),
	})
	if reasonCode != "" {
		recorder.summary.ReasonCodes = appendUnique(recorder.summary.ReasonCodes, reasonCode)
	}
	return nil
}

func (recorder *Recorder) Fail(failedState string, failedTrigger string, reasonCode string, recoverable bool, message string, source string) {
	recorder.summary.State = failedState
	recorder.summary.OK = false
	recorder.summary.Blocked = true
	recorder.summary.FailedState = failedState
	recorder.summary.FailedTrigger = failedTrigger
	recorder.summary.FailureReasonCode = reasonCode
	recorder.summary.Recoverable = &recoverable
	recorder.summary.ReasonCodes = appendUnique(recorder.summary.ReasonCodes, reasonCode)
	if message != "" || reasonCode != "" {
		recorder.summary.Blockers = append(recorder.summary.Blockers, Blocker{
			Code:    reasonCode,
			Message: message,
			Source:  source,
		})
	}
}

func (recorder *Recorder) Complete() {
	recorder.summary.OK = true
	recorder.summary.Blocked = false
}

func (recorder *Recorder) Summary() Summary {
	summary := recorder.summary
	summary.States = append([]State(nil), recorder.summary.States...)
	summary.Triggers = append([]Trigger(nil), recorder.summary.Triggers...)
	summary.Transitions = append([]Transition(nil), recorder.summary.Transitions...)
	summary.Guards = append([]Guard(nil), recorder.summary.Guards...)
	summary.ReasonCodes = append([]string(nil), recorder.summary.ReasonCodes...)
	sort.Strings(summary.ReasonCodes)
	summary.Blockers = append([]Blocker(nil), recorder.summary.Blockers...)
	summary.SubFSMs = append([]ArtifactRef(nil), recorder.summary.SubFSMs...)
	summary.DebugArtifacts = append([]DebugArtifact(nil), recorder.summary.DebugArtifacts...)
	summary.Evidence = cloneMap(recorder.summary.Evidence)
	return summary
}

func (recorder *Recorder) DOTGraph() string {
	return recorder.machine.ToGraph()
}

func appendUnique(values []string, value string) []string {
	if value == "" {
		return values
	}
	for _, existing := range values {
		if existing == value {
			return values
		}
	}
	return append(values, value)
}

func cloneMap(input map[string]any) map[string]any {
	if len(input) == 0 {
		return nil
	}
	result := make(map[string]any, len(input))
	for key, value := range input {
		result[key] = value
	}
	return result
}
