from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from mcp_interface.protocol_server import ProtocolServer
from agents._md_style import REVIEW_FORMAT, CONTEXT_BLOCK
import os


class PIAgent:
    def __init__(self, llm_model="gpt-5.1"):
        self.llm = ChatOpenAI(model=llm_model, openai_api_key=os.getenv("OPENAI_API_KEY"))
        self.prompt_template = PromptTemplate(
            template="""
            You are a Principal Investigator reviewing a clinical trial protocol.
            Your focus is on the feasibility of the study, the scientific rigor, and patient safety from a research leadership perspective.
            Identify any potential issues that could lead to amendments, suggest improvements, and provide a clear rationale.

            Review the following protocol content:
            ---
            {protocol_content}
            ---

            Provide one `## ` section for each of the key areas below, in this order, using the
            exact section titles shown:

            ## 1. Overall Scientific Soundness and Relevance
            Assess whether the study rationale, design, and endpoints are scientifically sound and relevant.

            ## 2. Feasibility of Patient Recruitment and Retention
            Evaluate whether the eligibility criteria and study burden allow realistic recruitment and retention.

            ## 3. Adequacy of Safety Monitoring and Adverse Event Reporting
            Assess whether safety monitoring and AE/SAE reporting are sufficient to protect participants.

            ## 4. Clarity and Completeness of Study Objectives and Endpoints
            Check that primary and secondary objectives and endpoints are clearly defined and complete.

            ## 5. Potential for Bias or Ethical Concerns
            Identify possible sources of bias and any ethical concerns in the design or conduct.

            ## 6. Unclear or Contradictory Sections
            Flag any sections that are ambiguous, internally inconsistent, or contradictory.
            """
            + CONTEXT_BLOCK
            + REVIEW_FORMAT,
            input_variables=["protocol_content", "retrieved_context"]
        )
        self.chain = self.prompt_template | self.llm | StrOutputParser()

    def review_protocol(self, protocol_server: ProtocolServer, context: str = "") -> str:
        full_protocol = protocol_server.get_all_content()
        response = self.chain.invoke({
            "protocol_content": full_protocol,
            "retrieved_context": context or "(no additional context retrieved)",
        })
        return response
