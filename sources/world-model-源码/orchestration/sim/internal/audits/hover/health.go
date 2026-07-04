package hover

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	artifactlayout "navlab/orchestration-sim/internal/artifacts/layout"
)

type HoverHealthFinding struct {
	Code       string          `json:"code"`
	Message    string          `json:"message,omitempty"`
	Tier       HoverSourceTier `json:"tier,omitempty"`
	ReviewOnly bool            `json:"review_only,omitempty"`
	Source     string          `json:"source,omitempty"`
}

type HoverHealthProceed struct {
	SimAutoContinueAllowed     bool   `json:"sim_auto_continue_allowed"`
	RealOperatorConfirmAllowed bool   `json:"real_operator_confirm_allowed"`
	Reason                     string `json:"reason"`
}

type HoverHealthSummary struct {
	Schema                  string               `json:"schema"`
	DiagnosticOnly          bool                 `json:"diagnostic_only"`
	RuntimeControlUnchanged bool                 `json:"runtime_control_unchanged"`
	ArtifactDir             string               `json:"artifact_dir"`
	HealthBand              HoverHealthBand      `json:"health_band"`
	Proceed                 HoverHealthProceed   `json:"proceed"`
	HardBlockers            []HoverHealthFinding `json:"hard_blockers"`
	StatisticalWarnings     []HoverHealthFinding `json:"statistical_warnings"`
	ReviewOnlyFindings      []HoverHealthFinding `json:"review_only_findings"`
	Metrics                 []HoverMetricValue   `json:"metrics"`
	Sources                 map[string]any       `json:"sources"`
	Pairs                   map[string]any       `json:"pairs"`
	Registries              map[string]any       `json:"registries"`
	Evidence                map[string]any       `json:"evidence"`
}

type HoverHealthCohortSummary struct {
	Schema                  string         `json:"schema"`
	DiagnosticOnly          bool           `json:"diagnostic_only"`
	RuntimeControlUnchanged bool           `json:"runtime_control_unchanged"`
	SampleSize              int            `json:"sample_size"`
	SampleSizeRule          string         `json:"sample_size_rule"`
	BandCounts              map[string]int `json:"band_counts"`
	Runs                    []any          `json:"runs"`
	Metrics                 map[string]any `json:"metrics"`
}

func BuildHoverHealthAudit(artifactDir string) (*HoverHealthSummary, error) {
	trajectory, err := BuildHoverTrajectoryAudit(artifactDir)
	if err != nil {
		return nil, fmt.Errorf("build trajectory audit: %w", err)
	}
	contract, err := BuildHoverContractAudit(artifactDir)
	if err != nil {
		return nil, fmt.Errorf("build contract audit: %w", err)
	}
	summary := &HoverHealthSummary{
		Schema:                  "navlab.hover_health_summary.v1",
		DiagnosticOnly:          true,
		RuntimeControlUnchanged: true,
		ArtifactDir:             artifactDir,
		HealthBand:              HoverHealthGreen,
		HardBlockers:            []HoverHealthFinding{},
		StatisticalWarnings:     []HoverHealthFinding{},
		ReviewOnlyFindings:      []HoverHealthFinding{},
		Metrics:                 []HoverMetricValue{},
		Sources:                 summarizeHoverHealthSources(trajectory, contract),
		Pairs:                   map[string]any{},
		Registries: map[string]any{
			"sources": hoverHealthSourceRegistry,
			"pairs":   hoverHealthPairRegistry,
		},
		Evidence: map[string]any{
			"trajectory_schema": trajectory["schema"],
			"contract_schema":   contract["schema"],
		},
	}
	summary.addPairMetrics(trajectory)
	summary.addContractFindings(contract)
	summary.addTopLevelSummaryFindings(artifactDir)
	summary.finishProceed()
	return summary, nil
}

func BuildHoverHealthCohort(artifactDirs []string) (*HoverHealthCohortSummary, error) {
	cohort := &HoverHealthCohortSummary{
		Schema:                  "navlab.hover_health_cohort.v1",
		DiagnosticOnly:          true,
		RuntimeControlUnchanged: true,
		SampleSize:              len(artifactDirs),
		SampleSizeRule:          hoverHealthSampleSizeRule(len(artifactDirs)),
		BandCounts:              map[string]int{},
		Runs:                    []any{},
		Metrics:                 map[string]any{},
	}
	metricValues := map[string][]float64{}
	metricSpecs := map[string]HoverMetricValue{}
	missionSpanValues := []float64{}
	missionSpanTargetExceeds := 0
	missionSpanHardCapExceeds := 0
	startupPolicyOutcomeCounts := map[string]int{}
	for _, artifactDir := range artifactDirs {
		audit, err := BuildHoverHealthAudit(artifactDir)
		if err != nil {
			return nil, fmt.Errorf("build health audit for %s: %w", artifactDir, err)
		}
		missionSpan := missionHoverSpanMetric(artifactDir)
		cohort.BandCounts[string(audit.HealthBand)]++
		runRow := map[string]any{
			"artifact_dir":                  artifactDir,
			"summary_artifact":              filepath.Join(artifactDir, "summary.json"),
			"mission_summary_artifact":      filepath.Join(artifactDir, "mission_summary.json"),
			"hover_health_artifact":         artifactlayout.Audit(artifactDir, "hover_health_summary.json"),
			"contract_audit_artifact":       artifactlayout.Audit(artifactDir, "contract_audit.json"),
			"trajectory_audit_artifact":     artifactlayout.Audit(artifactDir, "trajectory_audit.json"),
			"health_band":                   audit.HealthBand,
			"hard_blocker_count":            len(audit.HardBlockers),
			"statistical_warning_count":     len(audit.StatisticalWarnings),
			"review_only_finding_count":     len(audit.ReviewOnlyFindings),
			"sim_auto_continue_allowed":     audit.Proceed.SimAutoContinueAllowed,
			"real_operator_confirm_allowed": audit.Proceed.RealOperatorConfirmAllowed,
		}
		if missionSpan != nil {
			runRow["mission_hover_span"] = missionSpan
			if value, ok := finiteMetric(missionSpan, "horizontal_span_m"); ok {
				missionSpanValues = append(missionSpanValues, value)
				if exceeded, _ := missionSpan["target_exceeded"].(bool); exceeded {
					missionSpanTargetExceeds++
				}
				if exceeded, _ := missionSpan["hard_cap_exceeded"].(bool); exceeded {
					missionSpanHardCapExceeds++
				}
			}
		}
		if outcome := startupReadinessRuntimeOutcome(artifactDir); outcome != "" {
			runRow["startup_readiness_policy_outcome"] = outcome
			runRow["startup_readiness_runtime_artifact"] = artifactlayout.Audit(artifactDir, "startup_readiness_runtime.json")
			startupPolicyOutcomeCounts[outcome]++
		}
		cohort.Runs = append(cohort.Runs, runRow)
		for _, metric := range audit.Metrics {
			metricValues[metric.Key] = append(metricValues[metric.Key], metric.Value)
			metricSpecs[metric.Key] = metric
		}
	}
	if len(missionSpanValues) > 0 {
		cohort.Metrics["mission_hover_horizontal_span_m"] = map[string]any{
			"count":                 len(missionSpanValues),
			"unit":                  "m",
			"tier":                  HoverTierARealFlightSafety,
			"target_max":            0.10,
			"hard_max":              0.15,
			"sample_size_rule":      cohort.SampleSizeRule,
			"target_exceed_count":   missionSpanTargetExceeds,
			"hard_cap_exceed_count": missionSpanHardCapExceeds,
			"target_exceed_rate":    float64(missionSpanTargetExceeds) / float64(len(missionSpanValues)),
			"hard_cap_exceed_rate":  float64(missionSpanHardCapExceeds) / float64(len(missionSpanValues)),
			"p50":                   percentileFloat64(missionSpanValues, 0.50),
			"p90":                   percentileFloat64(missionSpanValues, 0.90),
			"p95":                   percentileFloat64(missionSpanValues, 0.95),
			"p99":                   percentileFloat64(missionSpanValues, 0.99),
			"max":                   percentileFloat64(missionSpanValues, 1.00),
		}
	}
	if len(startupPolicyOutcomeCounts) > 0 {
		cohort.Metrics["startup_readiness_policy_outcomes"] = map[string]any{
			"counts":   startupPolicyOutcomeCounts,
			"artifact": "audits/startup_readiness_runtime.json",
		}
	}
	for key, values := range metricValues {
		spec := metricSpecs[key]
		cohort.Metrics[key] = map[string]any{
			"count":       len(values),
			"unit":        spec.Unit,
			"tier":        spec.Tier,
			"target_max":  spec.TargetMax,
			"hard_max":    spec.HardMax,
			"review_only": spec.ReviewOnly,
			"p50":         percentileFloat64(values, 0.50),
			"p90":         percentileFloat64(values, 0.90),
			"p95":         percentileFloat64(values, 0.95),
			"p99":         percentileFloat64(values, 0.99),
			"max":         percentileFloat64(values, 1.00),
		}
	}
	return cohort, nil
}

func missionHoverSpanMetric(artifactDir string) map[string]any {
	path := filepath.Join(artifactDir, "mission_summary.json")
	payload := map[string]any{}
	if err := readHoverHealthJSON(path, &payload); err != nil {
		return nil
	}
	hoverDrift := mapFromAny(payload["hover_drift"])
	if hoverDrift == nil {
		return nil
	}
	value, ok := finiteMetric(hoverDrift, "horizontal_span_m")
	if !ok {
		return nil
	}
	target := metricFloat(hoverDrift, "hover_span_target_m")
	if target <= 0 {
		target = metricFloat(payload, "hover_span_target_m")
	}
	if target <= 0 {
		target = metricFloat(hoverDrift, "max_horizontal_drift_m")
	}
	if target <= 0 {
		target = 0.10
	}
	hardCap := metricFloat(hoverDrift, "hover_span_hard_cap_m")
	if hardCap <= 0 {
		hardCap = metricFloat(payload, "hover_span_hard_cap_m")
	}
	if hardCap <= 0 {
		hardCap = target
	}
	tier, _ := hoverDrift["horizontal_span_tier"].(string)
	if tier == "" {
		switch {
		case value <= target:
			tier = "green"
		case value <= hardCap:
			tier = "yellow"
		default:
			tier = "red"
		}
	}
	return map[string]any{
		"artifact":          filepath.Join(artifactDir, "mission_summary.json"),
		"horizontal_span_m": value,
		"target_m":          target,
		"hard_cap_m":        hardCap,
		"tier":              tier,
		"target_exceeded":   value > target,
		"hard_cap_exceeded": value > hardCap,
	}
}

func finiteMetric(payload map[string]any, key string) (float64, bool) {
	if !metricNumberPresent(payload, key) {
		return 0, false
	}
	value := metricFloat(payload, key)
	return value, true
}

func hoverHealthSampleSizeRule(size int) string {
	switch {
	case size < 10:
		return "case_study_only"
	case size < 30:
		return "exploratory_distribution"
	case size < 100:
		return "provisional_p90_p95"
	case size < 300:
		return "stable_p95"
	default:
		return "p99_meaningful"
	}
}

func summarizeHoverHealthSources(trajectory map[string]any, contract map[string]any) map[string]any {
	out := map[string]any{}
	trajectorySources := mapFromAny(trajectory["sources"])
	contractTopics := mapFromAny(contract["topics"])
	for _, spec := range hoverHealthSourceRegistry {
		row := map[string]any{
			"topic":    spec.Topic,
			"tier":     spec.Tier,
			"role":     spec.Role,
			"required": spec.Required,
		}
		if source := mapFromAny(trajectorySources[spec.Key]); source != nil {
			row["trajectory"] = subsetMap(source,
				"sample_count", "raw_sample_count", "max_horizontal_drift_m", "x_span_m", "y_span_m",
				"final_x_m", "final_y_m", "first_time_sec_from_bag_start", "last_time_sec_from_bag_start",
			)
		}
		if topic := hoverHealthContractTopic(contractTopics, spec); topic != nil {
			row["contract"] = topic["observed"]
		}
		out[spec.Key] = row
	}
	return out
}

func hoverHealthContractTopic(contractTopics map[string]any, spec HoverSourceSpec) map[string]any {
	if topic := mapFromAny(contractTopics[spec.Key]); topic != nil {
		return topic
	}
	for _, raw := range contractTopics {
		topic := mapFromAny(raw)
		if topic["topic"] == spec.Topic {
			return topic
		}
	}
	return nil
}

func (summary *HoverHealthSummary) addPairMetrics(trajectory map[string]any) {
	pairwise := mapFromAny(trajectory["pairwise_aligned_relative_motion"])
	for _, pairSpec := range hoverHealthPairRegistry {
		pairRow := firstPairRow(pairwise, pairSpec.LeftKey, pairSpec.RightKey)
		if pairRow == nil {
			continue
		}
		metricName, value := preferredPairMetric(pairRow)
		metricSpec := hoverHealthPairMetricSpec(pairSpec, metricName)
		metric := metricSpec.Classify(value)
		metric.PairKey = pairSpec.Key
		summary.Metrics = append(summary.Metrics, metric)
		summary.Pairs[pairSpec.Key] = map[string]any{
			"left_key":    pairSpec.LeftKey,
			"right_key":   pairSpec.RightKey,
			"tier":        pairSpec.Tier,
			"review_only": pairSpec.ReviewOnly,
			"metric":      metric,
			"evidence":    pairRow,
		}
		summary.applyMetric(metric)
	}
}

func firstPairRow(pairwise map[string]any, leftKey string, rightKey string) map[string]any {
	if pairwise == nil {
		return nil
	}
	if row := mapFromAny(pairwise[leftKey+"__"+rightKey]); row != nil {
		return row
	}
	return mapFromAny(pairwise[rightKey+"__"+leftKey])
}

func preferredPairMetric(pairRow map[string]any) (string, float64) {
	for _, candidate := range []struct {
		field string
		name  string
	}{
		{field: "p95_relative_vector_difference_m", name: "p95_error_m"},
		{field: "max_relative_vector_difference_m", name: "max_error_m"},
		{field: "mean_relative_vector_difference_m", name: "mean_error_m"},
	} {
		if metricNumberPresent(pairRow, candidate.field) {
			return candidate.name, metricFloat(pairRow, candidate.field)
		}
	}
	return "relative_error_m", 0
}

func (summary *HoverHealthSummary) applyMetric(metric HoverMetricValue) {
	summary.HealthBand = worseHoverBand(summary.HealthBand, metric.Band)
	finding := HoverHealthFinding{
		Code:       metric.Key + ":" + metric.Reason,
		Message:    metric.Description,
		Tier:       metric.Tier,
		ReviewOnly: metric.ReviewOnly,
		Source:     "hover_health_metric",
	}
	if metric.Severity == HoverMetricHard {
		summary.HardBlockers = append(summary.HardBlockers, finding)
		return
	}
	if metric.Severity == HoverMetricWarning {
		if metric.ReviewOnly {
			summary.ReviewOnlyFindings = append(summary.ReviewOnlyFindings, finding)
		} else {
			summary.StatisticalWarnings = append(summary.StatisticalWarnings, finding)
		}
	}
}

func (summary *HoverHealthSummary) addContractFindings(contract map[string]any) {
	for _, code := range stringsFromAny(contract["blockers"]) {
		finding := HoverHealthFinding{Code: code, Source: "contract_audit"}
		tier := tierForContractBlocker(code)
		finding.Tier = tier
		if tier == HoverTierARealFlightSafety && strings.HasPrefix(code, "missing:") {
			summary.HardBlockers = append(summary.HardBlockers, finding)
			summary.HealthBand = HoverHealthRed
			continue
		}
		if tier == HoverTierARealFlightSafety {
			summary.StatisticalWarnings = append(summary.StatisticalWarnings, finding)
			summary.HealthBand = worseHoverBand(summary.HealthBand, HoverHealthYellow)
			continue
		}
		if tier == HoverTierCLegacyDiagnostic {
			continue
		}
		finding.ReviewOnly = true
		summary.ReviewOnlyFindings = append(summary.ReviewOnlyFindings, finding)
		summary.HealthBand = worseHoverBand(summary.HealthBand, HoverHealthYellow)
	}
}

func tierForContractBlocker(code string) HoverSourceTier {
	if idx := strings.LastIndex(code, ":"); idx >= 0 && idx+1 < len(code) {
		if spec, ok := hoverHealthSourceByTopic(code[idx+1:]); ok {
			return spec.Tier
		}
	}
	for _, spec := range hoverHealthSourceRegistry {
		if strings.Contains(code, spec.Topic) || strings.Contains(code, spec.Key) {
			return spec.Tier
		}
	}
	if strings.Contains(code, "gazebo") {
		return HoverTierBReviewOnly
	}
	return HoverTierCLegacyDiagnostic
}

func (summary *HoverHealthSummary) addTopLevelSummaryFindings(artifactDir string) {
	path := filepath.Join(artifactDir, "summary.json")
	payload := map[string]any{}
	if err := readHoverHealthJSON(path, &payload); err != nil {
		return
	}
	for _, blocker := range blockersFromSummaryJSON(payload) {
		code := blocker.Code
		if code == "" {
			continue
		}
		finding := HoverHealthFinding{Code: code, Message: blocker.Message, Source: "summary_json"}
		if summaryBlockerIsReviewOnly(code) {
			finding.Tier = HoverTierBReviewOnly
			finding.ReviewOnly = true
			summary.ReviewOnlyFindings = append(summary.ReviewOnlyFindings, finding)
			summary.HealthBand = worseHoverBand(summary.HealthBand, HoverHealthYellow)
			continue
		}
		if summaryBlockerIsHardSafety(code) {
			finding.Tier = HoverTierARealFlightSafety
			summary.HardBlockers = append(summary.HardBlockers, finding)
			summary.HealthBand = HoverHealthRed
		}
	}
}

type hoverSummaryBlocker struct {
	Code    string
	Message string
}

func blockersFromSummaryJSON(payload map[string]any) []hoverSummaryBlocker {
	out := []hoverSummaryBlocker{}
	raw, ok := payload["blockers"].([]any)
	if !ok {
		return out
	}
	for _, item := range raw {
		switch typed := item.(type) {
		case string:
			out = append(out, hoverSummaryBlocker{Code: typed})
		case map[string]any:
			code, _ := typed["code"].(string)
			message, _ := typed["message"].(string)
			out = append(out, hoverSummaryBlocker{Code: code, Message: message})
		}
	}
	return out
}

func summaryBlockerIsReviewOnly(code string) bool {
	return strings.Contains(code, "gazebo") || strings.Contains(code, "review_only")
}

func summaryBlockerIsHardSafety(code string) bool {
	for _, token := range []string{"external_nav_loss", "mavlink_external_nav_loss", "slam_quality_lost", "pose_or_yaw_jump", "source_selector_not_ready", "frame_contract", "mission_abort"} {
		if strings.Contains(code, token) {
			return true
		}
	}
	return false
}

func (summary *HoverHealthSummary) finishProceed() {
	summary.Proceed = HoverHealthProceed{
		SimAutoContinueAllowed:     summary.HealthBand == HoverHealthGreen,
		RealOperatorConfirmAllowed: summary.HealthBand == HoverHealthGreen,
		Reason:                     "health_green",
	}
	switch summary.HealthBand {
	case HoverHealthRed:
		summary.Proceed.Reason = "health_red_abort_or_land"
	case HoverHealthYellow:
		summary.Proceed.Reason = "health_yellow_continue_hover_and_collect_stats"
	}
}

func startupReadinessRuntimeOutcome(artifactDir string) string {
	payload := map[string]any{}
	if err := readHoverHealthJSON(artifactlayout.Audit(artifactDir, "startup_readiness_runtime.json"), &payload); err != nil {
		return ""
	}
	decision := mapFromAny(payload["final_decision"])
	action, _ := decision["action"].(string)
	reason, _ := decision["reason"].(string)
	if strings.TrimSpace(action) == "" {
		return ""
	}
	if strings.TrimSpace(reason) == "" {
		return action
	}
	return action + ":" + reason
}

func readHoverHealthJSON(path string, out any) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(data, out)
}
