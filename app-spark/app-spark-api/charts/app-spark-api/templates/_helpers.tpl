{{/* Keep resource names and selectors consistent with the reference chart. */}}
{{- define "app-spark-api.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "app-spark-api.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{- define "app-spark-api.selectorLabels" -}}
app.kubernetes.io/name: {{ include "app-spark-api.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "app-spark-api.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "app-spark-api.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "app-spark-api.image" -}}
{{- printf "%s:%s" .Values.image.repository (.Values.image.tag | default .Chart.AppVersion) -}}
{{- end -}}

{{/* A fresh Job per Helm revision avoids modifying immutable Job pod templates. */}}
{{- define "app-spark-api.migrateJobName" -}}
{{- printf "%s-migrate-%d" (include "app-spark-api.fullname" . | trunc 50 | trimSuffix "-") (int .Release.Revision) -}}
{{- end -}}

{{/* Dynaconf @json preserves types, including numeric-looking passwords as strings. */}}
{{- define "app-spark-api.envValue" -}}
{{- printf "@json %s" (mustToJson .) | quote -}}
{{- end -}}
