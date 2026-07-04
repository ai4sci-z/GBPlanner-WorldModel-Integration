package helpers

import (
	"strings"
	"testing"
)

func TestRuntimeScriptTemplatesRenderScanReferenceWrappers(t *testing.T) {
	drift, err := ScanReferenceDriftRuntimeScript(DefaultScanReferenceDriftSpec())
	if err != nil {
		t.Fatalf("ScanReferenceDriftRuntimeScript() error = %v", err)
	}
	for _, want := range []string{
		"from navlab.sim.companion.nodes.scan_reference_drift import run",
		`\"scan_topic\":\"/scan\"`,
		`\"reset_on_hover_hold\"`,
		"reset-on-hover-hold",
	} {
		if !strings.Contains(drift, want) {
			t.Fatalf("drift wrapper missing %q:\n%s", want, drift)
		}
	}

	correction, err := ScanReferenceCorrectionRuntimeScript(DefaultScanReferenceCorrectionSpec())
	if err != nil {
		t.Fatalf("ScanReferenceCorrectionRuntimeScript() error = %v", err)
	}
	for _, want := range []string{
		"from navlab.sim.companion.nodes.scan_reference_correction import run",
		`\"output_odom_topic\":\"/slam/odom_corrected\"`,
		"enable-correction",
	} {
		if !strings.Contains(correction, want) {
			t.Fatalf("correction wrapper missing %q:\n%s", want, correction)
		}
	}
	if count := strings.Count(correction, "raise SystemExit(main())"); count != 1 {
		t.Fatalf("correction wrapper SystemExit count = %d, want 1:\n%s", count, correction)
	}

	selector, err := ExternalNavSourceSelectorRuntimeScript(DefaultExternalNavSourceSelectorSpec())
	if err != nil {
		t.Fatalf("ExternalNavSourceSelectorRuntimeScript() error = %v", err)
	}
	for _, want := range []string{
		"from navlab.sim.companion.nodes.external_nav_source_selector import run",
		`\"output_odom_topic\":\"/external_nav/odom_candidate\"`,
		"cartographer-disagreement-m",
	} {
		if !strings.Contains(selector, want) {
			t.Fatalf("selector wrapper missing %q:\n%s", want, selector)
		}
	}
}

func TestRuntimeScriptTemplatesRenderMissionAndNavigationWrappers(t *testing.T) {
	cases := []struct {
		name   string
		render func() (string, error)
		want   []string
	}{
		{
			name: "hover mission",
			render: func() (string, error) {
				return HoverMissionRuntimeScript(DefaultHoverMissionRuntimeSpec(), 12.5)
			},
			want: []string{
				"from navlab.sim.companion.nodes.hover_mission import run",
				`\"duration_sec\":12.5`,
				`\"operator_confirm_required\":false`,
				"hover-health-min-observation-sec",
				"mission_summary.json",
				"hover_mission_rc.txt",
			},
		},
		{
			name: "slam only probe",
			render: func() (string, error) {
				return SlamOnlyProbeScript(DefaultSlamOnlySpec(), 9.0)
			},
			want: []string{
				`\"slam_odom_topic\":\"/slam/odom\"`,
				"navlab_slam_only_probe",
				"slam_only_external_nav_quality_fields_missing",
			},
		},
		{
			name: "exploration workflow",
			render: func() (string, error) {
				return ExplorationWorkflowRuntimeScript(DefaultExplorationWorkflowSpec(), 13.0)
			},
			want: []string{
				`\"strategy\":\"frontier_lite\"`,
				"navlab_exploration_workflow",
				"publish_review_topics",
			},
		},
		{
			name: "navigation adapter",
			render: func() (string, error) {
				return NavigationAdapterRuntimeScript(DefaultNav2NavigationSpec(), 12.5)
			},
			want: []string{
				"RUN_UNTIL = time.monotonic() + 12.500",
				"navlab_navigation_adapter",
				`\"Profile\":\"indoor_2d\"`,
			},
		},
		{
			name: "navigation mission",
			render: func() (string, error) {
				return NavigationMissionRuntimeScript(DefaultNav2NavigationSpec(), 14.25)
			},
			want: []string{
				"RUN_UNTIL = time.monotonic() + 14.250",
				"mission_complete",
				"navigate_to_pose",
			},
		},
		{
			name: "nav2 lifecycle",
			render: func() (string, error) {
				return Nav2LifecycleProbeScript(DefaultNav2NavigationSpec())
			},
			want: []string{
				"LIFECYCLE_NODES",
				"navlab_nav2_lifecycle_probe",
				`\"PlannerPlugin\":\"GridBased\"`,
			},
		},
		{
			name: "costmap health",
			render: func() (string, error) {
				return CostmapHealthProbeScript(DefaultNav2NavigationSpec())
			},
			want: []string{
				"navlab_costmap_health_probe",
				"navigation_costmap_unknown_ratio_too_high",
				`\"CostmapHealthTopic\"`,
			},
		},
		{
			name: "navigation status",
			render: func() (string, error) {
				return NavigationStatusProbeScript(DefaultNav2NavigationSpec())
			},
			want: []string{
				"navigation_status_missing",
				"navigation_adapter_not_active",
				`\"NavigationStatusTopic\"`,
			},
		},
		{
			name: "ros probe",
			render: func() (string, error) {
				return rosProbeScript("navlab_test_probe", []string{"/scan", "/navlab/test/status"}, map[string]any{"ProbeTimeoutSec": 3.0})
			},
			want: []string{
				`"node": "navlab_test_probe"`,
				`TOPICS = json.loads("[\"/scan\",\"/navlab/test/status\"]")`,
				`OPTIONAL_TOPICS = set(json.loads("[]"))`,
				`\"ProbeTimeoutSec\":3`,
				`STRING_READY_TIMEOUT_SEC = max(STRING_BATCH_TIMEOUT_SEC, PROBE_TIMEOUT_SEC)`,
				`sample["failure_kind"] = "sample_stdout_present_timeout"`,
				`"failure_kind": "topic_type_missing"`,
				`sample["failure_kind"] = "topic_sample_missing"`,
			},
		},
		{
			name: "fcu controller",
			render: func() (string, error) {
				return FCUControllerRuntimeScript(DefaultFCUControllerSpec(), 12.0)
			},
			want: []string{
				"navlab_fcu_controller",
				`\"control_route\":\"mavlink_bootstrap_plus_dds_cmd_vel\"`,
				"task_completion_status_topic",
			},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got, err := tc.render()
			if err != nil {
				t.Fatalf("render() error = %v", err)
			}
			if strings.Contains(got, "{{") {
				t.Fatalf("rendered template still has template action:\n%s", got)
			}
			for _, want := range tc.want {
				if !strings.Contains(got, want) {
					t.Fatalf("rendered wrapper missing %q:\n%s", want, got)
				}
			}
		})
	}
}
