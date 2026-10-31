@ai @validation @laya @quality @retry
Feature: Multi-Tier Prompt Validation and Laya Semantic Review
  As the quality assurance gatekeeper
  I want deterministic syntax checks, motion/framing regex rules, and an RL decision model
  So that defective, static, framed, or impoverished prompts are caught and corrected before reaching video generation

  Background:
    Given a raw JSON string returned by the prompt writer
    And an active segment plan with reference image tags

  Rule: Tier 1 & 2 enforce structural schema integrity and sealed-lips rigging

    @VALIDATE-01
    Scenario: Writer response parser verifies exact field ordering and shot body count
      Given a raw LLM reply lacking the required summary field
      When the engine executes WriterResponse.parse
      Then a ValidationError is raised identifying the missing required field
      And the prompt fails before reaching quality or semantic checks

    @VALIDATE-02
    Scenario: Sealed-lips rigging tail is verified or restored on silent passages
      Given a silent passage prompt missing the Subject Rigging sentence
      When schema validation evaluates the text
      Then the system detects the missing rigging block
      And the engine injects RIGGING_TAIL directly above the soundscape block

  Rule: Tier 3 deterministic Mondo quality gates detect motion and framing defects

    @VALIDATE-03
    Scenario Outline: Motion and framing regex rules reject static scenes and border artifacts
      Given a written prompt containing the phrase "<defect_phrase>"
      When the Mondo prompt_problems quality check analyzes the prompt
      Then the gate rejects the prompt with problem description "<expected_problem>"
      And the rejection is added to the passage validation report

      Examples:
        | defect_phrase               | expected_problem                                      |
        | the composition is static   | The prompt declares a still image                     |
        | subject remains motionless  | holds a static camera and describes the subject as    |
        | letterboxed image           | The prompt describes a framing device                 |
        | split-screen presentation   | The prompt describes a framing device                 |

  Rule: Tier 4 enforces renderer prompt length ceilings

    @VALIDATE-04
    Scenario: Context length ceiling rejects oversized prompts according to backend rate card
      Given the active renderer is Seedance 2 with a 10000 character ceiling
      And a generated prompt measuring 10500 characters
      When length validation evaluates the prompt text
      Then a problem is logged stating the prompt exceeds the maximum prompt characters
      And the passage is returned to the writer for compression

  Rule: Tier 5 Laya RL semantic decision model evaluates visual density and completeness

    @VALIDATE-05
    Scenario: Low visual density triggers semantic rejection with structural failure mode
      Given a structurally valid prompt that passes deterministic Mondo checks
      When Laya evaluates the Jev clipboard questions
      And the visual_density score is 2 or lower with confidence above 0.55
      And structural_completeness indicates "missing_action"
      Then Laya rejects the prompt with note "Semantic Validator rejected: Visual density scored 2/5."
      And the failure feedback incorporates "Give every shot a concrete action or movement."

    @VALIDATE-06
    Scenario: Restriction safety violation causes immediate prompt rejection
      Given a prompt reviewed by Laya semantic evaluation
      When restriction_adherence is classified as unsafe or ambiguous with confidence above 0.55
      Then Laya rejects the prompt for content safety violation
      And the prompt is submitted to the corrective retry loop

  Rule: Tier 6 automated corrective feedback loop guides writer retries

    @VALIDATE-07
    Scenario: Feedback formatting compiles validation errors into writer retry prompt
      Given a prompt that failed Mondo motion checks and Laya visual density
      When the worker prepares the next LLM attempt
      Then formatted retry feedback is appended under "Correct these validation failures"
      And the LLM is queried with the augmented instructions up to the attempt limit

    @VALIDATE-08
    Scenario: Malformed JSON output receives free retry without exhausting attempt budget
      Given an LLM writer attempt that produces invalid truncated non-JSON text
      When the worker detects broken JSON syntax
      Then the call counter increments but the attempt counter is preserved
      And the query is re-dispatched up to the maximum free retry limit

    @VALIDATE-09
    Scenario: Reasoning think blocks and markdown fences are cleanly stripped before JSON parsing
      Given an LLM writer reply wrapped in <think> reasoning tags and markdown code fences
      When escape_control_characters and WriterResponse.parse evaluate the raw reply
      Then the <think> block and surrounding commentary are stripped cleanly
      And the balanced JSON payload is parsed without consuming a retry

    @VALIDATE-10
    Scenario: Laya style_adherence divergence records advisory notes and triggers strict retry feedback
      Given a prompt evaluated by Laya where style_adherence is judged divergent with confidence 0.80
      When laya_style_feedback inspects the Laya response
      Then an advisory note is recorded for segNNN.advice.json
      And when strict_prompt_checks is enabled a corrective retry problem is returned


