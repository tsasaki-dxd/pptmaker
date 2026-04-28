"""
ACM certificate stack for the SPA's custom domain.

CloudFront only accepts ACM certificates issued in us-east-1, so this
stack lives there. The main AppStack stays in ap-northeast-1 and reads
the certificate via CDK cross-region references (set
``cross_region_references=True`` on both stacks).

DNS validation: the parent domain (``dx-design.co.jp``) is hosted on
スターサーバー, not Route53, so this stack cannot register the
validation record automatically. After ``cdk deploy Cert-prod`` starts:

  1. The ACM cert resource enters CREATE_IN_PROGRESS and stays there.
  2. Open AWS Console → ACM → the cert in pending state and copy the
     "CNAME name" / "CNAME value" shown under Domain validation.
  3. Add that CNAME to スターサーバー's DNS for the parent domain.
  4. ACM auto-detects the record (usually within 5–30 min). The CFN
     resource flips to CREATE_COMPLETE and the deploy proceeds.

We expose the cert ARN as a CfnOutput so AppStack (or operators) can
refer to it without going through cross-stack imports if needed.
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_certificatemanager as acm
from constructs import Construct


class CertStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id_: str,
        *,
        domain_name: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, id_, **kwargs)

        self.domain_name = domain_name
        self.certificate = acm.Certificate(
            self,
            "Certificate",
            domain_name=domain_name,
            # DNS validation lets ACM auto-renew once we bolt on the
            # validation CNAME. Email validation would require the
            # registrant's mail to be reachable, which we don't control.
            validation=acm.CertificateValidation.from_dns(),
        )

        cdk.CfnOutput(
            self,
            "CertificateArn",
            value=self.certificate.certificate_arn,
            description="ACM cert ARN — referenced by AppStack via cross-region",
        )
        cdk.CfnOutput(
            self,
            "CertDomainName",
            value=domain_name,
            description="Domain name covered by the certificate",
        )
        cdk.CfnOutput(
            self,
            "ValidationLookup",
            value=(
                "Open ACM console (us-east-1) and read the 'CNAME name' / "
                "'CNAME value' from the cert's Domain validation tab; "
                "add it to the parent DNS zone."
            ),
            description="Reminder: validation records are visible only in ACM Console",
        )
