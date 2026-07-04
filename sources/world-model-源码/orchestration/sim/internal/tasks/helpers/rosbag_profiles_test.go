package helpers

import "testing"

func TestMetadataCountsFromString(t *testing.T) {
	counts := MetadataCountsFromString(`
rosbag2_bagfile_information:
  topics_with_message_count:
    - topic_metadata:
        name: /scan
      message_count: 3
    - topic_metadata:
        name: /tf
      message_count: 0
`)
	if counts["/scan"] != 3 || counts["/tf"] != 0 {
		t.Fatalf("counts = %#v", counts)
	}
}
