"""现行有效反洗钱法律、规章条款合集。正文取自官方公布文本，按调查引用分篇。"""

from __future__ import annotations

from .knowledge_aml import AML_STATUTES
from .knowledge_cdd import CDD_STATUTES
from .knowledge_ctr import CTR_STATUTES
from .knowledge_ubo import UBO_STATUTES

STATUTES: list[dict] = [
    *AML_STATUTES,
    *CDD_STATUTES,
    *UBO_STATUTES,
    *CTR_STATUTES,
]
