package tui

import (
	"fmt"
	"os"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"

	"navlab/orchestration-sim/internal/tasks"
)

type ReplayModel struct {
	state             ReplayState
	width             int
	height            int
	panel             int
	selectedComponent int
	mode              string
	events            <-chan tasks.RuntimeEvent
	done              <-chan error
	liveDone          bool
	runError          string
	eventLog          []string
}

func NewReplayModel(state ReplayState) ReplayModel {
	return ReplayModel{state: state, width: 100, height: 32, mode: "replay"}
}

func NewLiveModel(state ReplayState, events <-chan tasks.RuntimeEvent, done <-chan error) ReplayModel {
	model := NewReplayModel(state)
	model.mode = "live"
	model.events = events
	model.done = done
	model.state.Status = "running"
	return model
}

func (model ReplayModel) Init() tea.Cmd {
	if model.mode == "live" {
		return tea.Batch(waitRuntimeEvent(model.events), waitRunDone(model.done), tickLogs())
	}
	return nil
}

func (model ReplayModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch typed := msg.(type) {
	case tea.WindowSizeMsg:
		model.width = typed.Width
		model.height = typed.Height
	case tea.KeyMsg:
		switch typed.String() {
		case "q", "ctrl+c", "esc":
			return model, tea.Quit
		case "tab":
			model.panel = (model.panel + 1) % 4
		case "up", "k":
			if model.selectedComponent > 0 {
				model.selectedComponent--
			}
		case "down", "j":
			if model.selectedComponent+1 < len(model.state.RuntimeComponents) {
				model.selectedComponent++
			}
		case "b":
			model.panel = 1
		case "a":
			model.panel = 2
		case "l":
			model.panel = 3
		}
	case runtimeEventMsg:
		if !typed.ok {
			return model, nil
		}
		model.applyRuntimeEvent(typed.event)
		return model, waitRuntimeEvent(model.events)
	case runDoneMsg:
		model.liveDone = true
		if typed.err != nil {
			model.runError = typed.err.Error()
			model.state.Status = "blocked"
			model.panel = 1
		}
		model.refreshReplay()
	case logTickMsg:
		if model.mode == "live" && !model.liveDone {
			return model, tickLogs()
		}
	}
	return model, nil
}

func (model ReplayModel) View() string {
	width := model.width
	if width < 72 {
		width = 72
	}
	contentWidth := width - 4
	state := model.state
	header := headerStyle.Width(contentWidth).Render(fmt.Sprintf(
		"NavLab Sim TUI | %s | %s | %s | %s",
		emptyString(state.TaskID, "unknown-task"),
		emptyString(state.RunID, "unknown-run"),
		emptyString(state.Status, "unknown"),
		model.mode,
	))

	leftWidth := contentWidth / 3
	middleWidth := contentWidth / 3
	rightWidth := contentWidth - leftWidth - middleWidth - 4
	runtime := panelStyle.Width(leftWidth).Render(section("Runtime", runtimeLines(state)))
	gates := panelStyle.Width(middleWidth).Render(section("Gates / Blockers", blockerLines(state)))
	artifacts := panelStyle.Width(rightWidth).Render(section("Artifacts", artifactLines(state)))
	logs := panelStyle.Width(contentWidth).Render(section("Logs", model.logLines()))
	footer := footerStyle.Width(contentWidth).Render("q quit | tab panel | up/down component | b blockers | l logs | a artifacts")

	return lipgloss.JoinVertical(
		lipgloss.Left,
		header,
		lipgloss.JoinHorizontal(lipgloss.Top, runtime, gates, artifacts),
		logs,
		footer,
	)
}

func runtimeLines(state ReplayState) []string {
	lines := []string{
		fmt.Sprintf("services=%d probes=%d rosbags=%d", state.RuntimeCounts.Services, state.RuntimeCounts.Probes, state.RuntimeCounts.Rosbags),
	}
	for _, component := range state.RuntimeComponents {
		lines = append(lines, fmt.Sprintf("%s %-24s %s", component.Kind, truncate(component.Name, 24), normalizeStatus(component.Status)))
	}
	if len(state.RuntimeComponents) == 0 {
		lines = append(lines, mutedStyle.Render("no runtime_plan components"))
	}
	return lines
}

func blockerLines(state ReplayState) []string {
	if state.Status == "blocked" || strings.Contains(strings.ToLower(state.Status), "blocked") {
		if len(state.Blockers) == 0 {
			return []string{warningStyle.Render("blocked"), "summary pending or runtime failed before summary"}
		}
	}
	if len(state.Missing) > 0 {
		lines := []string{warningStyle.Render("missing artifacts")}
		for _, missing := range state.Missing {
			lines = append(lines, "- "+missing)
		}
		return lines
	}
	if len(state.Blockers) == 0 {
		return []string{okStyle.Render("no blockers")}
	}
	lines := make([]string, 0, len(state.Blockers))
	for _, blocker := range state.Blockers {
		lines = append(lines, "- "+blocker)
	}
	return lines
}

func artifactLines(state ReplayState) []string {
	lines := []string{}
	if state.SummaryKind != "" {
		lines = append(lines, "summary="+state.SummaryKind)
	}
	for _, artifact := range state.Artifacts {
		lines = append(lines, fmt.Sprintf("%-18s %s", truncate(artifact.Type, 18), artifact.Status))
	}
	if len(lines) == 0 {
		lines = append(lines, mutedStyle.Render("no manifest artifacts"))
	}
	return lines
}

func (model ReplayModel) logLines() []string {
	state := model.state
	lines := []string{"artifact_dir=" + state.ArtifactDir}
	if model.runError != "" {
		lines = append(lines, "error="+model.runError)
	}
	if component, ok := model.selectedRuntimeComponent(); ok {
		lines = append(lines, fmt.Sprintf("selected=%s/%s status=%s", component.Kind, component.Name, normalizeStatus(component.Status)))
		if component.LogPath != "" {
			lines = append(lines, "log="+component.LogPath)
			if tail := tailFile(component.LogPath, 16); len(tail) > 0 {
				return append(lines, tail...)
			}
		}
	}
	if state.SummaryPath != "" {
		lines = append(lines, "summary_path="+state.SummaryPath)
	}
	if len(model.eventLog) > 0 {
		lines = append(lines, model.eventLog...)
		return lines
	}
	return append(lines, mutedStyle.Render("no component log tail available"))
}

func (model ReplayModel) selectedRuntimeComponent() (RuntimeComponent, bool) {
	if len(model.state.RuntimeComponents) == 0 {
		return RuntimeComponent{}, false
	}
	index := model.selectedComponent
	if index < 0 || index >= len(model.state.RuntimeComponents) {
		index = 0
	}
	return model.state.RuntimeComponents[index], true
}

func section(title string, lines []string) string {
	body := []string{titleStyle.Render(title)}
	body = append(body, lines...)
	return strings.Join(body, "\n")
}

func truncate(value string, maxLength int) string {
	if len(value) <= maxLength {
		return value
	}
	if maxLength <= 1 {
		return value[:maxLength]
	}
	return value[:maxLength-1] + "..."
}

func emptyString(value string, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func (model *ReplayModel) applyRuntimeEvent(event tasks.RuntimeEvent) {
	model.state.TaskID = firstString(model.state.TaskID, event.TaskID)
	model.state.RunID = firstString(model.state.RunID, event.RunID)
	model.state.Status = statusFromPhase(event.Phase, model.state.Status)
	if event.ComponentID != "" {
		model.updateComponent(event)
	}
	if event.Phase == "run.blocked" || event.Phase == "run.failed" || strings.Contains(event.Phase, "failed") {
		if event.Message != "" {
			model.state.Blockers = appendUnique(model.state.Blockers, event.Message)
		}
		model.panel = 1
	}
	if event.Phase == "summary.written" {
		model.state.SummaryPath = event.Artifact
		model.refreshReplay()
	}
	model.eventLog = appendTail(model.eventLog, eventLine(event), 80)
}

func (model *ReplayModel) updateComponent(event tasks.RuntimeEvent) {
	for index := range model.state.RuntimeComponents {
		component := &model.state.RuntimeComponents[index]
		if component.Kind == event.Component && component.Name == event.ComponentID {
			component.Status = statusFromPhase(event.Phase, component.Status)
			if event.Artifact != "" {
				component.LogPath = event.Artifact
			}
			return
		}
	}
	model.state.RuntimeComponents = append(model.state.RuntimeComponents, RuntimeComponent{
		Kind:    event.Component,
		Name:    event.ComponentID,
		Status:  statusFromPhase(event.Phase, "running"),
		LogPath: event.Artifact,
	})
}

func (model *ReplayModel) refreshReplay() {
	next, err := LoadReplay(model.state.ArtifactDir)
	if err != nil {
		return
	}
	statusByComponent := map[string]string{}
	for _, component := range model.state.RuntimeComponents {
		statusByComponent[component.Kind+"/"+component.Name] = component.Status
	}
	for index := range next.RuntimeComponents {
		key := next.RuntimeComponents[index].Kind + "/" + next.RuntimeComponents[index].Name
		if status := statusByComponent[key]; status != "" {
			next.RuntimeComponents[index].Status = status
		}
	}
	if model.runError != "" && len(next.Blockers) == 0 {
		next.Blockers = []string{model.runError}
		next.Status = "blocked"
	}
	model.state = next
}

func statusFromPhase(phase string, fallback string) string {
	switch {
	case phase == "run.completed":
		return "ok"
	case phase == "run.blocked":
		return "blocked"
	case phase == "run.failed":
		return "failed"
	case strings.HasSuffix(phase, ".starting"):
		return "starting"
	case strings.HasSuffix(phase, ".running"):
		return "running"
	case strings.HasSuffix(phase, ".waiting"):
		return "waiting"
	case strings.HasSuffix(phase, ".started"):
		return "running"
	case strings.HasSuffix(phase, ".finished"):
		return "ok"
	case strings.HasSuffix(phase, ".failed"):
		return "failed"
	case strings.HasSuffix(phase, ".stopping"):
		return "stopping"
	case strings.HasSuffix(phase, ".stopped"):
		return "stopped"
	default:
		return fallback
	}
}

func normalizeStatus(status string) string {
	switch status {
	case "TASK_STATUS_OK":
		return "ok"
	case "TASK_STATUS_BLOCKED":
		return "blocked"
	case "TASK_STATUS_ERROR":
		return "failed"
	default:
		return status
	}
}

func eventLine(event tasks.RuntimeEvent) string {
	component := event.ComponentID
	if component == "" {
		component = "run"
	}
	message := event.Message
	if message == "" {
		message = event.Phase
	}
	return fmt.Sprintf("%s %-20s %s", event.Phase, truncate(component, 20), message)
}

func appendUnique(values []string, value string) []string {
	for _, existing := range values {
		if existing == value {
			return values
		}
	}
	return append(values, value)
}

func appendTail(values []string, value string, limit int) []string {
	values = append(values, value)
	if len(values) <= limit {
		return values
	}
	return values[len(values)-limit:]
}

func tailFile(path string, limit int) []string {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	lines := strings.Split(strings.TrimRight(string(data), "\n"), "\n")
	if len(lines) > limit {
		lines = lines[len(lines)-limit:]
	}
	return lines
}

type runtimeEventMsg struct {
	event tasks.RuntimeEvent
	ok    bool
}

type runDoneMsg struct {
	err error
}

type logTickMsg struct{}

func waitRuntimeEvent(events <-chan tasks.RuntimeEvent) tea.Cmd {
	return func() tea.Msg {
		event, ok := <-events
		return runtimeEventMsg{event: event, ok: ok}
	}
}

func waitRunDone(done <-chan error) tea.Cmd {
	return func() tea.Msg {
		return runDoneMsg{err: <-done}
	}
}

func tickLogs() tea.Cmd {
	return tea.Tick(time.Second, func(time.Time) tea.Msg {
		return logTickMsg{}
	})
}

var (
	headerStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("12")).
			Padding(0, 1)
	titleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("14"))
	okStyle = lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color("10"))
	warningStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("11"))
	mutedStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("8"))
	panelStyle = lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			Padding(0, 1)
	footerStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("8")).
			Padding(0, 1)
)
