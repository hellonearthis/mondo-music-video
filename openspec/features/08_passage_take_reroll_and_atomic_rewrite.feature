@ai @takes @reroll @rewrite @rollback
Feature: Passage Take Reroll and Atomic Prompt Rewrite
  As a music video producer
  I want isolated clip rerolls, fresh prompt rewrites with vocabulary re-sampling, and atomic rollback
  So that individual passages can be iterated non-destructively without risking previous successful takes

  Background:
    Given a completed music video production with saved plan and takes records
    And the studio engine is idle

  Rule: Passage prompt rewrite automatically samples fresh setting and motif vocabulary

    @TAKES-01
    Scenario: Rewriting a passage prompt re-samples vocabulary slots and updates plan
      Given an existing passage with established setting and mechanism terms
      When an authorized rewrite request is submitted for the passage
      Then the replan_segment_vocabulary function collects existing terms into used vocabulary
      And a fresh variation seed is generated avoiding base seed collisions
      And new setting, mechanism, lighting, and costume terms are picked from unused pool entries
      And the writer, Mondo checks, and Laya review execute for that single passage
      And the updated segment is atomically persisted to plan.json and prepared.json

    @TAKES-02
    Scenario: Prompt rewrite failure restores original plan and prompts without corruption
      Given a passage rewrite is initiated
      When a failure occurs during LLM writing, Mondo validation, or memory release
      Then prompts.json, passage-plan-prompts.json, plan.json, and prepared.json are restored
      And the failed draft is saved under validation files without replacing active prompts

    @TAKES-06
    Scenario: Creative steering nudges passage rewrite toward a requested Thematic World and direction note
      Given an existing passage being rewritten with a requested world_id and creative direction note
      When replan_segment_vocabulary executes with world_id steering
      Then the passage vocabulary pools are overridden by the requested Thematic World canon
      And the passage creative direction note is injected into contextual vocabulary ranking and writer conceptual_theme

  Rule: Hand-edited prompts undergo full validation without skipping quality or Laya checks

    @TAKES-03
    Scenario Outline: Hand edits are checked and accepted only if they satisfy all gates
      Given an operator provides an edited prompt text that "<edit_quality>"
      When the edit_prompt action checks the candidate text
      Then the engine executes Mondo checks and Laya review without querying the LLM writer
      And the resulting take is recorded as "<validation_status>" with active take "<active_status>"

      Examples:
        | edit_quality                | validation_status  | active_status   |
        | passes all schema and gates | validated: true    | becomes active  |
        | contains static camera cues | validated: false   | stays unchanged |
        | lacks required rigging tail | validated: false   | stays unchanged |

  Rule: Passage clip rerolls generate new numbered takes on free local renderers

    @TAKES-04
    Scenario: Rerolling a segment renders a new take with next seed on local H3
      Given a completed production on the local_h3 backend
      When an authorized reroll_segment command is executed with confirm=true
      Then a new clip is rendered using the active validated prompt and new seed
      And the rendered video is recorded as take2 under takes.json
      And previous take1 files are preserved untouched on disk

  Rule: Final video reassembly compiles selected takes with cancellable encodes

    @TAKES-05
    Scenario: Re-encoding final video from chosen takes preserves earlier final versions
      Given a production with multiple passage takes available
      When reassemble_output builds the final video from selected takes
      Then the original video is backed up as music-video-v1.mp4
      And a fresh single-pass encode compiles the video to music-video-v2.mp4
      And subliminal flashes and burned captions are reapplied inside the encode graph
      And an operator cancellation halts the encode without corrupting existing versions

