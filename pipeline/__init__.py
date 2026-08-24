"""Query-driven NRI support pipeline.

Runtime modules never import evaluator gold.  The server attaches evaluation
only after a complete runtime result has been produced.
"""

from .orchestrator import PipelineRunner

__all__ = ["PipelineRunner"]
