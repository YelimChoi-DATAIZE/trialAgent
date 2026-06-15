from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from mcp_interface.protocol_server import ProtocolServer
from agents._md_style import REVIEW_FORMAT, CONTEXT_BLOCK
import os

class SitePhysicianAgent:
    def __init__(self, llm_model="gpt-5.1"):
        """
        Initializes the SitePhysicianAgent with an LLM and a specific prompt.
        """
        self.llm = ChatOpenAI(model=llm_model, openai_api_key=os.getenv("OPENAI_API_KEY"))
        self.prompt_template = PromptTemplate(
            template="""
            You are a Site Physician reviewing a clinical trial protocol.
            Your focus is on the practical implementation at a clinical site, patient management, and operational challenges.
            Identify any potential issues that could lead to amendments, suggest improvements, and provide a clear rationale.

            Review the following protocol content:
            ---
            {protocol_content}
            ---

            Provide one `## ` section for each of the key areas below, in this order, using the
            exact section titles shown:

            ## 1. Practicality of Inclusion/Exclusion Criteria
            Assess if criteria are easily verifiable and don't overly restrict recruitment or burden staff.

            ## 2. Feasibility of Study Procedures and Visit Schedules
            Evaluate if the required procedures (e.g., lab tests, imaging, specific assessments) and their frequency are realistic for a busy clinical setting and manageable for patients.

            ## 3. Resource Requirements
            Consider demands on site staff (nurses, coordinators), equipment availability, and clinic space/time.

            ## 4. Patient Burden and Adherence
            Assess the overall burden on patients (e.g., number of visits, invasiveness of procedures, duration of study) and potential impact on adherence.

            ## 5. Clarity of Dosing, Administration, and Monitoring Instructions
            Ensure drug administration details, concomitant medication rules, and safety monitoring instructions are unambiguous for site staff.

            ## 6. Logistics of Drug Supply and Accountability
            Review procedures for receiving, storing, dispensing, and returning investigational product, as well as accountability requirements.

            ## 7. Overall Operational Workflow
            Any other operational challenges or potential bottlenecks in the study flow.
            """
            + CONTEXT_BLOCK
            + REVIEW_FORMAT,
            input_variables=["protocol_content", "retrieved_context"]
        )
        self.chain = self.prompt_template | self.llm | StrOutputParser()

    def review_protocol(self, protocol_server: ProtocolServer, context: str = "") -> str:
        """
        Reviews the clinical protocol from a Site Physician's perspective.
        Args:
            protocol_server: An instance of ProtocolServer to access protocol content.
            context: Optional shared-memory snippets retrieved by the reasoning step.
        Returns:
            A string containing the site physician's feedback and recommendations.
        """
        # For section-level summary, we still give the full protocol context for now
        # but the agent is prompted to focus on certain aspects.
        full_protocol = protocol_server.get_all_content()
        response = self.chain.invoke({
            "protocol_content": full_protocol,
            "retrieved_context": context or "(no additional context retrieved)",
        })
        return response