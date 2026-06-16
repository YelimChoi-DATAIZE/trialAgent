from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from agents._md_style import GENERATE_FORMAT, CONTEXT_BLOCK
import logging
import os

log = logging.getLogger("agent_server.protocol_generator")


class ProtocolGenerator:
    def __init__(self, llm_model="gpt-5.1"):
        self.llm = ChatOpenAI(model=llm_model, openai_api_key=os.getenv("OPENAI_API_KEY"))
        # Placeholder for dynamic template loading
        self.base_template = """
        You are an AI assistant specialized in drafting clinical trial protocols.
        Generate a clinical protocol based on the following details and follow ICH/FDA guidelines implicitly.

        Study Title: {study_title}
        Indication: {indication}
        Objectives: {objectives}

        ---
        ## 1. Introduction
        Elaborate on the disease background, unmet medical need, and rationale for the study.

        ## 2. Study Objectives
        Expand on the primary and secondary objectives.

        ## 3. Study Design
        Describe the study type (e.g., randomized, double-blind, placebo-controlled), phases, duration, and patient population.

        ## 4. Study Population
        Inclusion and Exclusion Criteria.

        ## 5. Study Procedures
        Outline visits, assessments, interventions, and data collection.

        ## 6. Statistical Considerations
        Sample size, endpoints, statistical methods.

        ## 7. Safety Reporting
        Adverse events, serious adverse events, reporting procedures.

        ## 8. Ethical Considerations
        Informed consent, IRB/IEC approval.

        ## 9. Data Management and Quality Control
        Data capture, quality assurance.

        ## 10. References
        Placeholder for references.
        ---
        """

    def load_template(self, template_path: str):
        """Loads a template from a specified path.

        Falls back to the built-in base template when the file is missing or empty.
        """
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            log.warning("Template not found at %s. Using default base template.", template_path)
            return self.base_template
        if not content.strip():
            log.warning("Template at %s is empty. Using default base template.", template_path)
            return self.base_template
        return content

    def generate_protocol_draft(self, study_title: str, indication: str, objectives: str,
                                template_path: str = None, context: str = "") -> str:
        if template_path:
            template = self.load_template(template_path)
        else:
            template = self.base_template

        prompt = PromptTemplate(
            template=template + CONTEXT_BLOCK + GENERATE_FORMAT,
            input_variables=["study_title", "indication", "objectives", "retrieved_context"]
        )
        chain = prompt | self.llm | StrOutputParser()
        response = chain.invoke({
            "study_title": study_title,
            "indication": indication,
            "objectives": objectives,
            "retrieved_context": context or "(no additional context retrieved)",
        })
        return response