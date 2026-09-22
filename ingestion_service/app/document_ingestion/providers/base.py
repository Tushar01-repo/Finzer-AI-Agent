from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

from app.document_ingestion.models import DiscoveredDocument


class DocumentProvider(ABC):
    """
    Base interface for external document discovery providers.

    Examples:
        - SEBI
        - NSE
        - BSE
        - Company investor-relations websites

    Provider responsibility ends at document discovery.

    A provider should:
        1. Discover documents.
        2. Extract source metadata.
        3. Return normalized DiscoveredDocument objects.

    A provider should NOT:
        - Download PDFs.
        - Parse PDFs.
        - Extract tables.
        - Detect document structure.
        - Create chunks.
        - Generate embeddings.
        - Write document contents to PostgreSQL.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        Stable identifier for the provider.

        Examples:
            sebi
            nse
            bse
        """
        raise NotImplementedError

    @abstractmethod
    def discover(
        self,
        *,
        start_page: int = 1,
        end_page: int | None = None,
    ) -> Iterator[DiscoveredDocument]:
        """
        Discover documents available from the provider.

        Args:
            start_page:
                First listing page to process.

            end_page:
                Last listing page to process.

                If None, the provider may continue until
                no additional pages are available.

        Yields:
            Normalized DiscoveredDocument objects.

        Important:
            Discovery should not download the PDF itself.
            The PDF downloader is a separate component.
        """
        raise NotImplementedError