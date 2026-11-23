"""Configura auto-scaling del endpoint (1 a 2 instancias segun invocaciones por instancia).

Si el Learner Lab lo bloquea, guarda la captura del error y justificalo en el informe.
"""
import boto3

REGION = "us-east-1"
RESOURCE_ID = "endpoint/autorecommend-endpoint/variant/AllTraffic"
DIMENSION = "sagemaker:variant:DesiredInstanceCount"

aas = boto3.client("application-autoscaling", region_name=REGION)
aas.register_scalable_target(
    ServiceNamespace="sagemaker", ResourceId=RESOURCE_ID,
    ScalableDimension=DIMENSION, MinCapacity=1, MaxCapacity=2,
)
aas.put_scaling_policy(
    PolicyName="invocations-per-instance",
    ServiceNamespace="sagemaker", ResourceId=RESOURCE_ID, ScalableDimension=DIMENSION,
    PolicyType="TargetTrackingScaling",
    TargetTrackingScalingPolicyConfiguration={
        "TargetValue": 100.0,
        "PredefinedMetricSpecification": {"PredefinedMetricType": "SageMakerVariantInvocationsPerInstance"},
        "ScaleInCooldown": 300,
        "ScaleOutCooldown": 60,
    },
)
print("Auto-scaling configurado: min 1, max 2 instancias")
