package helpers

import (
	"bytes"
	"embed"
	"text/template"
)

//go:embed templates/python/*.tmpl templates/yaml/*.tmpl templates/sdf/*.tmpl templates/sdf/fixtures/*.tmpl templates/parm/*.tmpl
var helperTemplates embed.FS

type runtimeScriptTemplateData struct {
	SpecJSON           string
	TopicsJSON         string
	OptionalTopicsJSON string
	NodeName           string
	DurationSec        float64
}

func renderRuntimeScriptTemplate(name string, payload []byte) (string, error) {
	return renderRuntimeScriptTemplateData(name, runtimeScriptTemplateData{SpecJSON: string(payload)})
}

func renderRuntimeScriptTemplateData(name string, data runtimeScriptTemplateData) (string, error) {
	return renderHelperTemplate("python/"+name, data)
}

func renderHelperTemplate(name string, data any) (string, error) {
	tmpl, err := template.ParseFS(helperTemplates, "templates/"+name)
	if err != nil {
		return "", err
	}
	var output bytes.Buffer
	err = tmpl.Execute(&output, data)
	if err != nil {
		return "", err
	}
	return output.String(), nil
}

func RenderStaticHelperTemplate(name string) (string, error) {
	return renderHelperTemplate(name, nil)
}

func mustRenderHelperTemplate(name string, data any) string {
	rendered, err := renderHelperTemplate(name, data)
	if err != nil {
		panic(err)
	}
	return rendered
}
