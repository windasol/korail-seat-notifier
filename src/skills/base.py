"""스킬 기본 인터페이스

모든 스킬은 BaseSkill을 상속하여 단일 책임 원칙을 따른다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T_In = TypeVar("T_In")
T_Out = TypeVar("T_Out")


class BaseSkill(ABC, Generic[T_In, T_Out]):
    """스킬 기본 인터페이스

    규칙:
    - 단일 책임: 하나의 명확한 작업만 수행
    - 상태 비공유: 에이전트를 통해서만 데이터 전달
    - 실패 격리: 개별 스킬 실패가 다른 스킬에 영향 없음
    - 테스트 가능: 모든 스킬에 단위 테스트 필수
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """스킬 고유 이름"""

    @abstractmethod
    async def execute(self, input_data: T_In) -> T_Out:
        """스킬 실행"""

    async def setup(self) -> None:
        """초기화 (선택적 오버라이드)"""

    async def teardown(self) -> None:
        """정리 (선택적 오버라이드)"""
