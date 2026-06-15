from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from mcp_interface.protocol_server import ProtocolServer
from agents._md_style import REVIEW_FORMAT, CONTEXT_BLOCK
import os


class HealthAuthorityAgent:
    def __init__(self, llm_model="gpt-5.1"):
        """
        Initializes the HealthAuthorityAgent with an LLM and a specific prompt.
        """
        self.llm = ChatOpenAI(model=llm_model, openai_api_key=os.getenv("OPENAI_API_KEY"))
        self.prompt_template = PromptTemplate(
            template="""
            You are a Health Authority/Regulatory Compliance Agent reviewing a clinical trial protocol.
            Your focus is on adherence to regulatory guidelines (ICH-GCP, FDA, EMA as applicable), ethical considerations, and data integrity.
            Identify any potential issues that could lead to amendments, suggest improvements, and provide a clear rationale.

            Review the following protocol content:
            ---
            {protocol_content}
            ---

            Provide one `## ` section for each of the key areas below, in this order, using the
            exact section titles shown:

            ## 1. Compliance with Regulatory Guidelines (ICH-GCP, FDA, EMA)
            Assess if all relevant sections conform to international and regional regulatory requirements.

            ## 2. Adequacy of Informed Consent Process
            Review whether the informed consent process is clearly defined, addresses all necessary elements, and ensures patient understanding and voluntary participation.

            ## 3. Data Management and Quality Assurance Procedures
            Evaluate the robustness of data collection, handling, validation, and storage procedures to ensure data integrity and traceability.

            ## 4. Statistical Analysis Plan Rigor and Appropriateness
            Assess if the statistical methods are appropriate for the study objectives and endpoints, and if the sample size justification is sound from a regulatory perspective.

            ## 5. Safety Reporting Mechanisms and Adverse Event Definitions
            Verify that AE/SAE definitions, reporting timelines, and follow-up procedures are clear, compliant with regulations, and ensure patient safety monitoring.

            ## 6. Overall Ethical Soundness
            Review the ethical aspects of the study design, including patient welfare, risks vs. benefits, vulnerable populations, and privacy safeguards.

            ## 7. Any Ambiguities in Regulatory Phrasing
            Identify any language that could be interpreted differently or is not precise enough for regulatory clarity.
            """
            + CONTEXT_BLOCK
            + REVIEW_FORMAT,
            input_variables=["protocol_content", "retrieved_context"]
        )
        self.chain = self.prompt_template | self.llm | StrOutputParser()

    def review_protocol(self, protocol_server: ProtocolServer, context: str = "") -> str:
        """
        Reviews the clinical protocol from a Health Authority/Regulatory Compliance perspective.
        Args:
            protocol_server: An instance of ProtocolServer to access protocol content.
            context: Optional shared-memory snippets retrieved by the reasoning step.
        Returns:
            A string containing the health authority's feedback and recommendations.
        """
        # For section-level summary, we still give the full protocol context for now
        # but the agent is prompted to focus on certain aspects.
        full_protocol = protocol_server.get_all_content()
        response = self.chain.invoke({
            "protocol_content": full_protocol,
            "retrieved_context": context or "(no additional context retrieved)",
        })
        return response