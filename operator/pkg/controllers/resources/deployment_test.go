/*
 * TencentBlueKing is pleased to support the open source community by making
 * 蓝鲸智云 - PaaS 平台 (BlueKing - PaaS System) available.
 * Copyright (C) 2017 THL A29 Limited, a Tencent company. All rights reserved.
 * Licensed under the MIT License (the "License"); you may not use this file except
 * in compliance with the License. You may obtain a copy of the License at
 *
 *	http://opensource.org/licenses/MIT
 *
 * Unless required by applicable law or agreed to in writing, software distributed under
 * the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND,
 * either express or implied. See the License for the specific language governing permissions and
 * limitations under the License.
 *
 * We undertake not to change the open source license (MIT license) applicable
 * to the current version of the project delivered to anyone in the future.
 */

package resources

import (
	. "github.com/onsi/ginkgo/v2"
	. "github.com/onsi/gomega"
	appsv1 "k8s.io/api/apps/v1"
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/runtime"
	"sigs.k8s.io/controller-runtime/pkg/client/fake"

	"bk.tencent.com/paas-app-operator/api/v1alpha1"
	paasv1alpha2 "bk.tencent.com/paas-app-operator/api/v1alpha2"
	"bk.tencent.com/paas-app-operator/pkg/controllers/resources/labels"
	"bk.tencent.com/paas-app-operator/pkg/utils/kubetypes"
)

var _ = Describe("Test build deployments from BkApp", func() {
	var bkapp *paasv1alpha2.BkApp
	var builder *fake.ClientBuilder
	var scheme *runtime.Scheme

	BeforeEach(func() {
		bkapp = &paasv1alpha2.BkApp{
			TypeMeta: metav1.TypeMeta{
				Kind:       paasv1alpha2.KindBkApp,
				APIVersion: paasv1alpha2.GroupVersion.String(),
			},
			ObjectMeta: metav1.ObjectMeta{
				Name:      "bkapp-sample",
				Namespace: "default",
			},
			Spec: paasv1alpha2.AppSpec{
				Build: paasv1alpha2.BuildConfig{
					Image: "nginx:latest",
				},
				Processes: []paasv1alpha2.Process{
					{
						Name:         "web",
						Replicas:     paasv1alpha2.ReplicasTwo,
						ResQuotaPlan: "default",
						TargetPort:   80,
					},
					{
						Name:         "hi",
						Replicas:     paasv1alpha2.ReplicasTwo,
						ResQuotaPlan: "default",
						Command:      []string{"/bin/sh"},
						Args:         []string{"-c", "echo hi"},
					},
				},
				Configuration: paasv1alpha2.AppConfig{
					Env: []paasv1alpha2.AppEnvVar{
						{Name: "ENV_NAME_1", Value: "env_value_1"},
						{Name: "ENV_NAME_2", Value: "env_value_2"},
					},
				},
				// Add some overlay configs
				EnvOverlay: &paasv1alpha2.AppEnvOverlay{
					Replicas: []paasv1alpha2.ReplicasOverlay{
						{EnvName: "stag", Process: "web", Count: 10},
					},
					EnvVariables: []paasv1alpha2.EnvVarOverlay{
						{EnvName: "stag", Name: "ENV_NAME_3", Value: "env_value_3"},
						{EnvName: "prod", Name: "ENV_NAME_1", Value: "env_value_1_prod"},
					},
				},
			},
		}

		builder = fake.NewClientBuilder()
		scheme = runtime.NewScheme()
		Expect(paasv1alpha2.AddToScheme(scheme)).NotTo(HaveOccurred())
		Expect(appsv1.AddToScheme(scheme)).NotTo(HaveOccurred())
		Expect(corev1.AddToScheme(scheme)).NotTo(HaveOccurred())
		builder.WithScheme(scheme)
	})

	Context("basic fields checks", func() {
		It("no processes", func() {
			bkapp.Spec.Processes = []paasv1alpha2.Process{}
			deploys := GetWantedDeploys(bkapp)
			Expect(len(deploys)).To(Equal(0))
		})

		It("common base fields", func() {
			deploys := GetWantedDeploys(bkapp)
			Expect(len(deploys)).To(Equal(2))

			webDeploy := deploys[0]
			Expect(webDeploy.APIVersion).To(Equal("apps/v1"))
			Expect(webDeploy.Kind).To(Equal("Deployment"))
			Expect(webDeploy.Name).To(Equal("bkapp-sample--web"))
			Expect(webDeploy.Namespace).To(Equal(bkapp.Namespace))
			Expect(webDeploy.Labels).To(Equal(labels.Deployment(bkapp, "web")))
			Expect(webDeploy.OwnerReferences[0].Kind).To(Equal(bkapp.Kind))
			Expect(webDeploy.OwnerReferences[0].Name).To(Equal(bkapp.Name))
			Expect(len(webDeploy.Spec.Template.Spec.Containers)).To(Equal(1))

			hiDeploy := deploys[1]
			Expect(hiDeploy.Name).To(Equal("bkapp-sample--hi"))
			Expect(hiDeploy.Spec.Selector.MatchLabels).To(Equal(labels.Deployment(bkapp, "hi")))
			Expect(*hiDeploy.Spec.RevisionHistoryLimit).To(Equal(int32(0)))
			Expect(len(hiDeploy.Spec.Template.Spec.Containers)).To(Equal(1))
		})
	})

	Context("container basic fields", func() {
		It("base fields", func() {
			bkapp.Spec.Build = paasv1alpha2.BuildConfig{
				Image: "busybox:latest",
			}
			bkapp.Spec.Processes = []paasv1alpha2.Process{{
				Name:       "web",
				Replicas:   paasv1alpha2.ReplicasOne,
				Command:    []string{"/bin/sh"},
				Args:       []string{"-c", "echo hi"},
				TargetPort: 8081,
			}}

			c := GetWantedDeploys(bkapp)[0].Spec.Template.Spec.Containers[0]
			Expect(len(c.Command)).To(Equal(1))
			Expect(len(c.Args)).To(Equal(2))
			Expect(c.Ports).To(Equal([]corev1.ContainerPort{{ContainerPort: 8081}}))
		})
	})

	Context("Image related fields", func() {
		It("default version", func() {
			bkapp.Spec.Build = paasv1alpha2.BuildConfig{
				Image:           "busybox:latest",
				ImagePullPolicy: corev1.PullAlways,
			}
			bkapp.Spec.Processes = []paasv1alpha2.Process{
				{
					Name:     "web",
					Replicas: paasv1alpha2.ReplicasOne,
				}, {
					Name:     "worker",
					Replicas: paasv1alpha2.ReplicasOne,
				},
			}

			cWeb := GetWantedDeploys(bkapp)[0].Spec.Template.Spec.Containers[0]
			Expect(cWeb.Name).To(Equal("web"))
			Expect(cWeb.Image).To(Equal("busybox:latest"))
			Expect(cWeb.ImagePullPolicy).To(Equal(corev1.PullAlways))

			cWorker := GetWantedDeploys(bkapp)[1].Spec.Template.Spec.Containers[0]
			Expect(cWorker.Name).To(Equal("worker"))
			Expect(cWorker.Image).To(Equal(cWeb.Image))
			Expect(cWorker.ImagePullPolicy).To(Equal(cWeb.ImagePullPolicy))
		})

		It("legacy version", func() {
			kubetypes.SetJsonAnnotation(bkapp, paasv1alpha2.LegacyProcImageAnnoKey, paasv1alpha2.LegacyProcConfig{
				"web":    {"image": "busybox:1.0.0", "policy": "Never"},
				"worker": {"image": "busybox:2.0.0", "policy": "Always"},
			})
			bkapp.Spec.Build = paasv1alpha2.BuildConfig{}
			bkapp.Spec.Processes = []paasv1alpha2.Process{
				{
					Name:     "web",
					Replicas: paasv1alpha2.ReplicasOne,
				}, {
					Name:     "worker",
					Replicas: paasv1alpha2.ReplicasOne,
				},
			}

			cWeb := GetWantedDeploys(bkapp)[0].Spec.Template.Spec.Containers[0]
			Expect(cWeb.Image).To(Equal("busybox:1.0.0"))
			Expect(cWeb.ImagePullPolicy).To(Equal(corev1.PullNever))

			cWorker := GetWantedDeploys(bkapp)[1].Spec.Template.Spec.Containers[0]
			Expect(cWorker.Image).To(Equal("busybox:2.0.0"))
			Expect(cWorker.ImagePullPolicy).To(Equal(corev1.PullAlways))
		})
	})

	Context("Resources related fields", func() {
		BeforeEach(func() {
			bkapp.Spec.Build = paasv1alpha2.BuildConfig{
				Image:           "busybox:latest",
				ImagePullPolicy: corev1.PullAlways,
			}
		})
		It("default version", func() {
			bkapp.Spec.Processes = []paasv1alpha2.Process{
				{
					Name:         "web",
					Replicas:     paasv1alpha2.ReplicasOne,
					ResQuotaPlan: "default",
				}, {
					Name:         "worker",
					Replicas:     paasv1alpha2.ReplicasOne,
					ResQuotaPlan: "default",
				},
			}

			cWebRes := GetWantedDeploys(bkapp)[0].Spec.Template.Spec.Containers[0].Resources
			cWorkerRes := GetWantedDeploys(bkapp)[1].Spec.Template.Spec.Containers[0].Resources
			// The processes should share the same resource requirements
			Expect(cWebRes.Requests).To(Equal(cWorkerRes.Requests))
			Expect(cWebRes.Limits).To(Equal(cWorkerRes.Limits))

			// The resource requirements should be the default value defined in project config
			// TODO: enhance below tests to check real plans
			Expect(cWebRes.Limits.Cpu().String()).To(Equal(v1alpha1.ProjConf.ResLimitConfig.ProcDefaultCPULimits))
			Expect(cWebRes.Limits.Memory().String()).To(Equal(v1alpha1.ProjConf.ResLimitConfig.ProcDefaultMemLimits))
		})

		It("legacy version", func() {
			kubetypes.SetJsonAnnotation(bkapp, paasv1alpha2.LegacyProcResAnnoKey, paasv1alpha2.LegacyProcConfig{
				"web":    {"cpu": "1", "memory": "1Gi"},
				"worker": {"cpu": "2", "memory": "2Gi"},
			})
			bkapp.Spec.Processes = []paasv1alpha2.Process{
				{
					Name:     "web",
					Replicas: paasv1alpha2.ReplicasOne,
				}, {
					Name:     "worker",
					Replicas: paasv1alpha2.ReplicasOne,
				},
			}

			// Check resource requirements for "web"
			cWebRes := GetWantedDeploys(bkapp)[0].Spec.Template.Spec.Containers[0].Resources
			Expect(cWebRes.Requests.Cpu().String()).To(Equal("250m"))
			Expect(cWebRes.Limits.Cpu().String()).To(Equal("1"))
			Expect(cWebRes.Requests.Memory().String()).To(Equal("512Mi"))
			Expect(cWebRes.Limits.Memory().String()).To(Equal("1Gi"))

			// Check resource requirements for "worker"
			cWorkerRes := GetWantedDeploys(bkapp)[1].Spec.Template.Spec.Containers[0].Resources
			Expect(cWorkerRes.Requests.Cpu().String()).To(Equal("500m"))
			Expect(cWorkerRes.Limits.Cpu().String()).To(Equal("2"))
			Expect(cWorkerRes.Requests.Memory().String()).To(Equal("1Gi"))
			Expect(cWorkerRes.Limits.Memory().String()).To(Equal("2Gi"))
		})
	})

	Context("environment related fields", func() {
		It("stag env related fields", func() {
			bkapp.SetAnnotations(map[string]string{paasv1alpha2.EnvironmentKey: "stag"})
			deploys := GetWantedDeploys(bkapp)
			web, hi := deploys[0], deploys[1]
			// Value overwritten by overlay config
			Expect(*web.Spec.Replicas).To(Equal(int32(10)))
			Expect(*hi.Spec.Replicas).To(Equal(int32(2)))
			Expect(web.Spec.Template.Spec.Containers[0].Env).To(Equal(
				[]corev1.EnvVar{
					{Name: "ENV_NAME_1", Value: "env_value_1"},
					{Name: "ENV_NAME_2", Value: "env_value_2"},
					// Env var appended by overlay config
					{Name: "ENV_NAME_3", Value: "env_value_3"},
				},
			))
		})
		It("prod env related fields", func() {
			bkapp.SetAnnotations(map[string]string{paasv1alpha2.EnvironmentKey: "prod"})
			deploys := GetWantedDeploys(bkapp)
			web, hi := deploys[0], deploys[1]
			Expect(*web.Spec.Replicas).To(Equal(int32(2)))
			Expect(*hi.Spec.Replicas).To(Equal(int32(2)))
			Expect(web.Spec.Template.Spec.Containers[0].Env).To(Equal(
				[]corev1.EnvVar{
					// Env var overwritten by overlay config
					{Name: "ENV_NAME_1", Value: "env_value_1_prod"},
					{Name: "ENV_NAME_2", Value: "env_value_2"},
				},
			))
		})
	})
})
