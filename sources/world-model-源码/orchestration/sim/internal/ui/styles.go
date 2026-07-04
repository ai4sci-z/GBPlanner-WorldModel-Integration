package ui

import (
	"fmt"

	"github.com/charmbracelet/lipgloss"
)

var (
	titleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("12"))
	okStyle = lipgloss.NewStyle().
		Bold(true).
		Foreground(lipgloss.Color("10"))
	errorStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("9"))
	keyStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("14"))
	taskIDStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("11"))
	subtitleStyle = lipgloss.NewStyle().
			Bold(true).
			Foreground(lipgloss.Color("13"))
	stepNumberStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("8"))
	mutedStyle = lipgloss.NewStyle().
			Foreground(lipgloss.Color("8"))
)

func Title(value string) string {
	return titleStyle.Render(value)
}

func StatusOK(value string) string {
	return okStyle.Render("OK") + " " + value
}

func Error(value string) string {
	return errorStyle.Render(value)
}

func KeyValue(key string, value any) string {
	return fmt.Sprintf("%s=%v", keyStyle.Render(key), value)
}

func TaskID(value string) string {
	return taskIDStyle.Render(value)
}

func Subtitle(value string) string {
	return subtitleStyle.Render(value)
}

func StepNumber(value int) string {
	return stepNumberStyle.Render(fmt.Sprintf("%d.", value))
}

func Muted(value string) string {
	return mutedStyle.Render(value)
}
