{{- define "wids.labels" -}}
app.kubernetes.io/part-of: wids
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
