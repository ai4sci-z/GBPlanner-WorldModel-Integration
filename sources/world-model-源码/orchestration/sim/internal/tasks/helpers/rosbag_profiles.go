package helpers

import (
	"regexp"
	"strconv"
	"strings"
)

func MetadataCountsFromString(content string) map[string]int {
	counts := map[string]int{}
	topicPattern := regexp.MustCompile(`name: (/[^\n]+)`)
	countPattern := regexp.MustCompile(`message_count:\s*(\d+)`)
	matches := topicPattern.FindAllStringSubmatchIndex(content, -1)
	for index, match := range matches {
		topic := strings.TrimSpace(content[match[2]:match[3]])
		end := len(content)
		if index+1 < len(matches) {
			end = matches[index+1][0]
		}
		block := content[match[1]:end]
		countMatch := countPattern.FindStringSubmatch(block)
		if len(countMatch) != 2 {
			counts[topic] = 0
			continue
		}
		count, err := strconv.Atoi(countMatch[1])
		if err != nil {
			count = 0
		}
		counts[topic] = count
	}
	return counts
}
