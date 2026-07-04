package tui

import "navlab/orchestration-sim/internal/tasks"

type ChannelEventSink struct {
	Events chan<- tasks.RuntimeEvent
}

func (sink ChannelEventSink) EmitRuntimeEvent(event tasks.RuntimeEvent) {
	if sink.Events == nil {
		return
	}
	sink.Events <- event
}
