#!/usr/bin/env python
"""
Prompt sets for LLM-based code generation.
Each prompt set contains structured prompts for different agent modes.
"""
from enum import Enum
from typing import Dict


class PromptSet:
    """A collection of prompts for code generation."""
    
    def __init__(
        self,
        name: str,
        io_contract: Dict[int, str],
        coding_prompt: Dict[int, str],
        requirements_prompt: Dict[int, str],
        tdd_prompt: Dict[int, str]
    ):
        self.name = name
        self.io_contract = io_contract
        self.coding_prompt = coding_prompt
        self.requirements_prompt = requirements_prompt
        self.tdd_prompt = tdd_prompt
    
    def build_io_contract(self) -> str:
        """Build the I/O contract prompt from indexed statements."""
        parts = []
        # Add header if present
        if 'header' in self.io_contract:
            parts.append(self.io_contract['header'])
        # Add all numbered statements in order
        numeric_keys = [k for k in self.io_contract.keys() if isinstance(k, int)]
        for i in sorted(numeric_keys):
            parts.append(self.io_contract[i])
        return "".join(parts)
    
    def build_coding_prompt(
        self,
        problem_description: str,
        io_contract: str,
        input_sample: str = ""
    ) -> str:
        """Build the single-agent coding prompt."""
        parts = []
        # Add role if present
        if 'role' in self.coding_prompt:
            parts.append(self.coding_prompt['role'])
        # Add all numbered statements in order
        numeric_keys = [k for k in self.coding_prompt.keys() if isinstance(k, int)]
        for i in sorted(numeric_keys):
            parts.append(self.coding_prompt[i])
        # Add sample input if present and provided
        if input_sample and 'sample_input' in self.coding_prompt:
            parts.append(self.coding_prompt['sample_input'].format(input_sample=input_sample))
        # Add problem description
        if 'problem' in self.coding_prompt:
            parts.append(self.coding_prompt['problem'].format(problem_description=problem_description))
        # Add I/O contract header if present
        if 'io_header' in self.coding_prompt:
            parts.append(self.coding_prompt['io_header'].format(io_contract=io_contract))
        else:
            # Fallback: include io_contract directly
            parts.append(f"I/O CONTRACT:\n{io_contract}\n")
        return "".join(parts)
    
    def build_requirements_prompt(
        self,
        problem_description: str,
        io_contract: str,
        input_sample: str = ""
    ) -> str:
        """Build the requirements agent prompt."""
        parts = []
        # Add role if present
        if 'role' in self.requirements_prompt:
            parts.append(self.requirements_prompt['role'])
        # Add all numbered statements in order
        numeric_keys = [k for k in self.requirements_prompt.keys() if isinstance(k, int)]
        for i in sorted(numeric_keys):
            parts.append(self.requirements_prompt[i])
        # Add sample input if present and provided
        if input_sample and 'sample_input' in self.requirements_prompt:
            parts.append(self.requirements_prompt['sample_input'].format(input_sample=input_sample))
        # Add problem description
        if 'problem' in self.requirements_prompt:
            parts.append(self.requirements_prompt['problem'].format(problem_description=problem_description))
        # Add I/O contract
        if 'io_header' in self.requirements_prompt:
            parts.append(self.requirements_prompt['io_header'].format(io_contract=io_contract))
        return "".join(parts)
    
    def build_tdd_prompt(
        self,
        structured_requirements: str,
        problem_description: str,
        io_contract: str,
        input_sample: str = ""
    ) -> str:
        """Build the TDD agent prompt."""
        parts = []
        # Add role if present
        if 'role' in self.tdd_prompt:
            parts.append(self.tdd_prompt['role'])
        # Add all numbered statements in order
        numeric_keys = [k for k in self.tdd_prompt.keys() if isinstance(k, int)]
        for i in sorted(numeric_keys):
            parts.append(self.tdd_prompt[i])
        # Add sample input if present and provided
        if input_sample and 'sample_input' in self.tdd_prompt:
            parts.append(self.tdd_prompt['sample_input'].format(input_sample=input_sample))
        # Add requirements
        if 'requirements' in self.tdd_prompt:
            parts.append(self.tdd_prompt['requirements'].format(structured_requirements=structured_requirements))
        # Add problem description
        if 'problem' in self.tdd_prompt:
            parts.append(self.tdd_prompt['problem'].format(problem_description=problem_description))
        # Add I/O contract
        if 'io_header' in self.tdd_prompt:
            parts.append(self.tdd_prompt['io_header'].format(io_contract=io_contract))
        return "".join(parts)
    
    def build_code_generation_prompt(
        self,
        structured_requirements: str,
        problem_description: str,
        io_contract: str,
        test_suite: str = "",
        input_sample: str = ""
    ) -> str:
        """Build the code generation agent prompt (multi-agent mode)."""
        prompt = (
            "Role: Expert Python engineer.\n\n"
            "Write ONE Python program.\n"
            "- Follow INPUT GRAMMAR.\n"
            "- Follow OUTPUT CONTRACT.\n"
            "- DO NOT validate or reject any lines.\n"
            "- DO NOT raise exceptions for unexpected formats.\n"
            "- Print ONLY the final numeric/string result.\n\n"
        )
        
        if test_suite:
            prompt += f"Acceptance Checks (NO CODE):\n{test_suite}\n\n"
        
        prompt += (
            f"Concise Requirements:\n{structured_requirements}\n\n"
            f"Problem Description:\n{problem_description}\n\n"
            f"I/O CONTRACT:\n{io_contract}\n"
        )
        
        if input_sample:
            prompt += (
                "Sample Input (first 5 lines):\n"
                f"{input_sample}\n\n"
            )
        
        return prompt
    
    def build_coding_agent_prompt(
        self,
        problem_description: str,
        io_contract: str,
        input_sample: str = ""
    ) -> str:
        """Build the coding-only agent prompt (for pipeline='c' in multi-agent mode)."""
        prompt = (
            "Role: Expert Python engineer.\n\n"
            "Write ONE Python program.\n"
            "- Follow INPUT GRAMMAR.\n"
            "- Follow OUTPUT CONTRACT.\n"
            "- DO NOT validate or reject any lines.\n"
            "- DO NOT raise exceptions for unexpected formats.\n"
            "- Print ONLY the final numeric/string result.\n\n"
            f"Problem Description:\n{problem_description}\n\n"
            f"I/O CONTRACT:\n{io_contract}\n"
        )
        
        if input_sample:
            prompt += (
                "Sample Input (first 5 lines):\n"
                f"{input_sample}\n\n"
            )
        
        return prompt

DEFAULT = PromptSet(
    name="DEFAULT",
    io_contract={
        'header': "I/O CONTRACT (NON-NEGOTIABLE):\n",
        1: "ALWAYS use sys.argv[1] and read that file.\n",
        2: "- IMPORTANT: `sys.argv[1]` is a path to a text file containing the problem input.\n",
        3: "- You MUST open and read that file (e.g. `with open(sys.argv[1]) as f:`).\n",
        4: "- Do NOT treat `sys.argv[1]` itself as the problem data.\n",
        5: "- Do NOT read from stdin unless the problem explicitly requires it.\n",
        6: "- Do NOT interpret additional argv items as problem data.\n",
        7: "- NEVER use f-strings for output formatting. ALWAYS finish with print(result).\n",
        8: "- NEVER try to validate, reject, or sanitize the input data itself.\n",
        9: "- NEVER raise exceptions about unexpected line formats.\n",
        10: " Print only the final answer.\n\n",
        11: " Parsing: Read all lines and strip whitespace; skip blank lines safely; treat other lines as meaningful records and parse them without raising exceptions.\n",
    },
    coding_prompt={
        'role': "Role: Expert Python engineer.\n\n",
        1: "Behavior Requirements:\n",
        2: "2. Write simple, straightforward code.\n",
        3: "3. DO NOT invent input formats.\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
    },
    requirements_prompt={
        'role': "You are an expert requirements engineer.\n\n",
        1: "Write A short list of edge cases.\n\n",
        2: "ABSOLUTELY DO NOT invent validation rules or reject input formats.\n",
        3: "Describe only what is observable in the description and sample.\n\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    },
    tdd_prompt={
        'role': "You are an expert TDD analyst.\n\n",
        1: "Write a SMALL Python test suite.\n",
        2: "Tests MUST NOT expect exceptions about invalid input.\n",
        3: "Assume all input is valid.\n\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'requirements': "Concise Requirements:\n{structured_requirements}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    }
)

POST_2021_CHECK = PromptSet(
    name="POST_2021_CHECK",
    io_contract={
        'header': "I/O CONTRACT (NON-NEGOTIABLE):\n",
        1: "ALWAYS use sys.argv[1] and read that file.\n",
        2: "- ⚠️ EXTREMELY IMPORTANT ⚠️: `sys.argv[1]` is a path to a text file containing the problem input.\n",
        3: "- You MUST open and read that file (e.g. `with open(sys.argv[1]) as f:`).\n",
        4: "- Do NOT treat `sys.argv[1]` itself as the problem data.\n",
        5: "- Do NOT read from stdin unless the problem explicitly requires it.\n",
        6: "- Do NOT interpret additional argv items as problem data.\n",
        7: "- NEVER use f-strings for output formatting. ALWAYS finish with print(result).\n",
        8: "- NEVER try to validate, reject, or sanitize the input data itself.\n",
        9: "- NEVER raise exceptions about unexpected line formats.\n",
        10: " Print only the final answer.\n\n",
    },
    coding_prompt={
        'role': "Role: Expert Python engineer.\n\n",
        1: "Behavior Requirements:\n",
        3: "3. DO NOT invent input formats.\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    },
    requirements_prompt={
        'role': "You are an expert requirements engineer.\n\n",
        1: "Write A short list of edge cases.\n\n",
        2: "ABSOLUTELY DO NOT invent validation rules or reject input formats.\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    },
    tdd_prompt={
        'role': "You are an expert TDD analyst.\n\n",
        1: "Write a SMALL Python test suite.\n",
        2: "Tests MUST NOT expect exceptions about invalid input.\n",
        3: "Assume all input is valid.\n\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'requirements': "Concise Requirements:\n{structured_requirements}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    }
)



SUPER_SIMPLE = PromptSet(
    name="SUPER_SIMPLE",
    io_contract={
        'header': "I/O CONTRACT (NON-NEGOTIABLE):\n",
        1: "ALWAYS use sys.argv[1] and read that file.\n",
        2: "- ⚠️ EXTREMELY IMPORTANT ⚠️: `sys.argv[1]` is a path to a text file containing the problem input.\n",
        3: "- You MUST open and read that file (e.g. `with open(sys.argv[1]) as f:`).\n",
        4: "- Do NOT treat `sys.argv[1]` itself as the problem data.\n",
        5: "- Do NOT read from stdin unless the problem explicitly requires it.\n",
        6: "- Do NOT interpret additional argv items as problem data.\n",
        7: "- NEVER use f-strings for output formatting. ALWAYS finish with print(result).\n",
        8: "- NEVER try to validate, reject, or sanitize the input data itself.\n",
        9: "- NEVER raise exceptions about unexpected line formats.\n",
        10: " Print only the final answer.\n\n",
    },
    coding_prompt={
        'role': "Role: Expert Python engineer.\n\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    },
    requirements_prompt={
        'role': "You are an expert requirements engineer.\n\n",
        1: "Write A short list of edge cases and complete list of requirements for the TDD agent to make his test suite.\n\n",
        2: "ABSOLUTELY DO NOT invent validation rules or reject input formats.\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    },
    tdd_prompt={
        'role': "You are an expert TDD analyst.\n\n",
        1: "Write a SMALL Python test suite for the coding agent.\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'requirements': "Concise Requirements:\n{structured_requirements}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    }
)


POST_2021_CHECK = PromptSet(
    name="POST_2021_CHECK",
    io_contract={
        'header': "I/O CONTRACT (NON-NEGOTIABLE):\n",
        1: "ALWAYS use sys.argv[1] and read that file.\n",
        2: "- ⚠️ EXTREMELY IMPORTANT ⚠️: `sys.argv[1]` is a path to a text file containing the problem input.\n",
        3: "- You MUST open and read that file (e.g. `with open(sys.argv[1]) as f:`).\n",
        4: "- Do NOT treat `sys.argv[1]` itself as the problem data.\n",
        5: "- Do NOT read from stdin unless the problem explicitly requires it.\n",
        6: "- Do NOT interpret additional argv items as problem data.\n",
        7: "- NEVER use f-strings for output formatting. ALWAYS finish with print(result).\n",
        8: "- NEVER try to validate, reject, or sanitize the input data itself.\n",
        9: "- NEVER raise exceptions about unexpected line formats.\n",
        10: " Print only the final answer.\n\n",
    },
    coding_prompt={
        'role': "Role: Expert Python engineer.\n\n",
        1: "Behavior Requirements:\n",
        3: "3. DO NOT invent input formats.\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    },
    requirements_prompt={
        'role': "You are an expert requirements engineer.\n\n",
        1: "Write A short list of edge cases.\n\n",
        2: "ABSOLUTELY DO NOT invent validation rules or reject input formats.\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    },
    tdd_prompt={
        'role': "You are an expert TDD analyst.\n\n",
        1: "Write a SMALL Python test suite.\n",
        2: "Tests MUST NOT expect exceptions about invalid input.\n",
        3: "Assume all input is valid.\n\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'requirements': "Concise Requirements:\n{structured_requirements}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    }
)

POST_2021_CASE_STUDIES = PromptSet(
    name="POST_2021_CASE_STUDIES",
    io_contract={
        'header': "I/O CONTRACT (NON-NEGOTIABLE):\n",
        1: "ALWAYS use sys.argv[1] and read that file.\n",
        2: "- `sys.argv[1]` is a path to a text file containing the problem input.\n",
        3: "- You MUST open and read that file (e.g. `with open(sys.argv[1]) as f:`).\n",
        4: "- Do NOT treat `sys.argv[1]` itself as the problem data.\n",
        5: "- Do NOT read from stdin unless the problem explicitly requires it.\n",
        6: "- OUTPUT CONTRACT: Print ONLY the final numeric/string answer, nothing else.\n",
    },
    coding_prompt={
        'role': "Role: Expert Python engineer.\n\n",
        1: "Behavior Requirements:\n",
        2: "2. Enforce I/O CONTRACT rules exactly (sys.argv[1], single-line output).\n",
        3: "3. DO NOT invent input formats not shown in examples.\n",
        4: "4. If examples show specific formats, treat them as assertions only, not exhaustive specs.\n",
        5: "5. The code must be executable as a script: `if __name__ == '__main__':`.\n",
        6: "6. OUTPUT CONTRACT: `print(result)` must output exactly one line.\n",
        7: "7. RECURSIVE TREE OPERATIONS: If implementing recursive functions that propagate values (e.g., left_val, right_val):\n"
                "   - SCOPE RULE (NON-NEGOTIABLE): NEVER reference undefined variables. If a function takes a parameter (e.g., `snailfish` or `node`), use THAT parameter; do not accidentally refer to a different free variable name inside loops (prevents NameError).\n"
                    "   - ALWAYS check `if isinstance(node, int):` at the START of recursive functions before accessing list indices\n"
                    "   - After replacements (e.g., pair→0), structure types change - must guard EVERY index access with type checks\n"
                    "   - ALWAYS check `if value is not None:` before using the value in operations\n"
                    "   - Never pass None to arithmetic operations - guard all propagation with None checks\n"
                    "   - If a function returns (tree, left_val, right_val), use left_val for left direction and right_val for right direction\n"
                    "   - Common bug: checking `if left_val is not None:` but then using `right_val` - DON'T MIX THESE UP\n"
                    "   - Helper functions that add values to trees MUST return the modified tree, not mutate in place\n"
                    "   - When accumulating results (e.g., adding list of numbers), start with FIRST element, not empty list\n"
                    "   - NEVER use list.index() to navigate nested structures - it only works for shallow lists\n"
                    "   - Tree navigation MUST be done recursively by following left/right child references, not by index searching\n"
                    "   - EXPLODE RETURN SIGNATURE (MANDATORY): implement explode as a helper that returns (new_node, left_carry, right_carry, did_explode)\n"
                    "     where left_carry/right_carry are ONLY `int` or `None` (NEVER a list/tree).\n"
                    "   - DO NOT destructure returns into wrong names/order; use clear variable names matching the signature (e.g., left_carry, right_carry).\n"
                    "   - Never return (node, None, node) or any mixed-type tuple; carry values must be scalars only.\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    },
    requirements_prompt={
        'role': "You are an expert requirements engineer.\n\n",
        1: "1. Write 3-6 bullet parsing/structure notes derived from the description (no invented edge cases).\n\n",
        2: "2. Explicitly mention any observable input section boundaries or blank-line separators.\n\n",
        3: "3. ABSOLUTELY DO NOT invent validation rules or reject input formats.\n",
        4: "4. If the problem statement contains explicit example input→output results, list up to 3 verbatim (no code, no tests).\n",
        5: "5. Do NOT include any code blocks or pseudo-code. If you must refer to an example, describe it in plain text only.\n",
        6: "6. RECURSIVE STRUCTURE DETECTION: If the description mentions nested pairs, nested lists, trees, recursive definitions, pairs within pairs, "
                    "or structures that contain themselves, you MUST add a bullet point that explicitly states: '⚠️ RECURSIVE/NESTED STRUCTURE: "
                    "This problem requires recursive tree traversal. Pairs/nodes can contain other pairs/nodes to arbitrary depth.'\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    },
    tdd_prompt={
        'role': "You are an expert TDD analyst.\n\n",
        1: "Write a Python test suite with pytest.\n",
        2: "Tests MUST NOT expect exceptions about invalid input.\n",
        3: "Use explicit example results from the problem description.\n",
        4: "Include at least one test per explicit example in the description.\n",
        5: "Tests must be self-contained (not read from sys.argv[1]).\n",
        6: "Assume all input is valid and well-formed.\n",
        7: "Test both simple cases AND complex cases from the description.\n",
        8: "RECURSIVE/NESTED STRUCTURE TESTS (CRITICAL): If the requirements mention recursive/nested/tree/pairs (or contain the ⚠️ flag), YOU MUST:\n"
                    "   a) Include a test with deeply nested input (depth >= 4) that would fail if structure is flattened.\n"
                    "   b) Include a test that performs exactly ONE explode and asserts it matches an example from the description.\n"
                    "   c) In test docstrings, write: 'REQUIRES RECURSIVE TRAVERSAL - will fail with flat iteration.'\n"
                    "   d) Include a test comment: '# This problem has nested/recursive structure - solution must recurse on sub-structures'\n"
                    "   e) DIRECTIONAL PROPAGATION TEST: Include a test that verifies values propagate in the correct direction (left vs right). "
                        "For example, if an operation returns (modified_tree, left_value, right_value), test that left_value affects left neighbors and right_value affects right neighbors. "
                        "Add comment: '# Test left/right propagation - common bug: mixing up which value goes which direction'\n"
                    "   f) TYPE-INVARIANT TEST: Add an assertion that explode-carry values are `int` or `None` only (never a list). This catches the common bug: int += list.\n",
        9: "TREE TRAVERSAL GUIDANCE: For nested structures, tests should verify that modifications propagate correctly through the tree (e.g., values added to left child affect result).\n",
        'sample_input': "Sample Input (first 5 lines):\n{input_sample}\n\n",
        'requirements': "Concise Requirements:\n{structured_requirements}\n\n",
        'problem': "Problem Description:\n{problem_description}\n\n",
        'io_header': "I/O CONTRACT:\n{io_contract}\n",
    }
)

# Temporary prompt set for analysis
REMOVED_io_contract_9 = PromptSet(
    name="REMOVED_io_contract_9",
    io_contract={'header': 'I/O CONTRACT (NON-NEGOTIABLE):\n', 1: 'ALWAYS use sys.argv[1] and read that file.\n', 2: '- `sys.argv[1]` is a path to a text file containing the problem input.\n', 3: '- You MUST open and read that file (e.g. `with open(sys.argv[1]) as f:`).\n', 4: '- Do NOT treat `sys.argv[1]` itself as the problem data.\n', 5: '- Do NOT read from stdin unless the problem explicitly requires it.\n', 6: '- Do NOT interpret additional argv items as problem data.\n', 7: '- NEVER use f-strings for output formatting. ALWAYS finish with print(result).\n', 8: '- NEVER try to validate, reject, or sanitize the input data itself.\n', 10: ' Print only the final answer.\n\n', 11: ' Parsing: Read all lines and strip whitespace; skip blank lines safely; treat other lines as meaningful records and parse them without raising exceptions.\n'},
    coding_prompt={'role': 'Role: Expert Python engineer.\n\n', 1: 'Behavior Requirements:\n', 2: '2. Write simple, straightforward code.\n', 3: '3. DO NOT invent input formats.\n', 'sample_input': 'Sample Input (first 5 lines):\n{input_sample}\n\n', 'problem': 'Problem Description:\n{problem_description}\n\n'},
    requirements_prompt={'role': 'You are an expert requirements engineer.\n\n', 1: 'Write A short list of edge cases.\n\n', 2: 'ABSOLUTELY DO NOT invent validation rules or reject input formats.\n', 3: 'Describe only what is observable in the description and sample.\n\n', 'sample_input': 'Sample Input (first 5 lines):\n{input_sample}\n\n', 'problem': 'Problem Description:\n{problem_description}\n\n', 'io_header': 'I/O CONTRACT:\n{io_contract}\n'},
    tdd_prompt={'role': 'You are an expert TDD analyst.\n\n', 1: 'Write a SMALL Python test suite.\n', 2: 'Tests MUST NOT expect exceptions about invalid input.\n', 3: 'Assume all input is valid.\n\n', 'sample_input': 'Sample Input (first 5 lines):\n{input_sample}\n\n', 'requirements': 'Concise Requirements:\n{structured_requirements}\n\n', 'problem': 'Problem Description:\n{problem_description}\n\n', 'io_header': 'I/O CONTRACT:\n{io_contract}\n'}
)

class PromptSetEnum(Enum):
    """Enumeration of available prompt sets."""
    DEFAULT = DEFAULT
    POST_2021_CHECK = POST_2021_CHECK
    POST_2021_CASE_STUDIES = POST_2021_CASE_STUDIES
    REMOVED_io_contract_9 = REMOVED_io_contract_9
    SUPER_SIMPLE = SUPER_SIMPLE
    



def get_prompt_set(name: str = "DEFAULT") -> PromptSet:
    """Get a prompt set by name."""
    try:
        return PromptSetEnum[name].value
    except KeyError:
        raise ValueError(f"Unknown prompt set: {name}. Available: {[e.name for e in PromptSetEnum]}")
