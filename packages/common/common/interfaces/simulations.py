"""
Abstract Repository Interfaces for User Simulation & Interactive Playground Data.
Compliant with Clean Architecture DDD.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ISimulationRunRepository(ABC):
    """Contract for persisting general simulation experiment runs."""

    @abstractmethod
    async def create_run(self, run_record: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def list_runs(
        self,
        user_id: Optional[str] = None,
        domain: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def delete_run(self, run_id: str) -> bool:
        pass


class IChatSessionRepository(ABC):
    """Contract for multi-turn chat sessions and message threads."""

    @abstractmethod
    async def create_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def list_sessions(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def add_message(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_session_messages(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        pass

    @abstractmethod
    async def create_prompt_template(self, template_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def list_prompt_templates(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        pass


class IOCRRecordRepository(ABC):
    """Contract for OCR document extractions."""

    @abstractmethod
    async def create_record(self, record_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def list_records(
        self, user_id: Optional[str] = None, doc_type: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        pass


class IEKYCSessionRepository(ABC):
    """Contract for eKYC biometric verification sessions."""

    @abstractmethod
    async def create_session(self, session_data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def list_sessions(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        pass


class IAudioRecordRepository(ABC):
    """Contract for Speech-to-Text and Text-to-Speech simulation records."""

    @abstractmethod
    async def create_transcription(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def list_transcriptions(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def create_synthesis(self, data: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    async def list_syntheses(self, user_id: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        pass
