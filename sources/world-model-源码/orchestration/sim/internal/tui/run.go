package tui

import (
	"fmt"
	"os"

	tea "github.com/charmbracelet/bubbletea"

	"navlab/orchestration-sim/internal/tasks"
)

type RunOptions struct {
	RequireTTY bool
}

func RunReplay(artifactDir string, options RunOptions) error {
	if options.RequireTTY {
		if err := EnsureInteractiveTerminal(); err != nil {
			return err
		}
	}
	state, err := LoadReplay(artifactDir)
	if err != nil {
		return err
	}
	program := tea.NewProgram(NewReplayModel(state), tea.WithAltScreen())
	if _, err := program.Run(); err != nil {
		return fmt.Errorf("failed to run sim tui: %w", err)
	}
	return nil
}

func RunLive(artifactDir string, run func(tasks.RuntimeEventSink) error, options RunOptions) error {
	if options.RequireTTY {
		if err := EnsureInteractiveTerminal(); err != nil {
			return err
		}
	}
	state, err := LoadReplay(artifactDir)
	if err != nil {
		return err
	}
	events := make(chan tasks.RuntimeEvent, 256)
	done := make(chan error, 1)
	resultDone := make(chan error, 1)
	go func() {
		defer close(events)
		err := run(ChannelEventSink{Events: events})
		done <- err
		resultDone <- err
	}()
	program := tea.NewProgram(NewLiveModel(state, events, done), tea.WithAltScreen())
	if _, err := program.Run(); err != nil {
		return fmt.Errorf("failed to run sim live tui: %w", err)
	}
	select {
	case err := <-resultDone:
		return err
	default:
	}
	return nil
}

func EnsureInteractiveTerminal() error {
	if !stdoutIsTerminal() {
		return fmt.Errorf("tui requires an interactive terminal; use plain output or run navlab-sim tui from a TTY")
	}
	return nil
}

func stdoutIsTerminal() bool {
	info, err := os.Stdout.Stat()
	if err != nil {
		return false
	}
	return info.Mode()&os.ModeCharDevice != 0
}
