@ai @llm @prompts @writer
Feature: LLM Segment Prompt Synthesis
  As the music video production engine
  I want to assemble structured prompt synthesis jobs and query a large language model
  So that each musical passage is translated into an expressive, timing-synchronized generative video prompt

  Background:
    Given a configured music-video prompt writer service
    And an aesthetic style card with directives loaded into memory

  Rule: System prompt composition injects domain constraints and content restrictions

    @WRITER-01
    Scenario: Silent mouths mode enforces sealed-lips rules and rigging examples
      Given a production with silent mouths enabled
      When the system prompt is composed for the prompt writer
      Then the prompt includes the exact sealed-lips rule text
      And the prompt includes the rigging example line specifying lips firmly sealed shut
      And the closing directive requires suppression of facial babbling and lip-sync hallucinations

    @WRITER-02
    Scenario: Singing mode substitutes natural mouth movement directives
      Given a production with singing mouths enabled for active singer passages
      When the system prompt is composed for the singing passage
      Then the prompt substitutes natural facial movement and mouth articulation rules
      And the sealed-lips rigging block is excised from aesthetic directives

    @WRITER-03
    Scenario: Content restriction overrides take precedence at the tail of the system prompt
      Given a production configured with content restrictions for nudity, blood, violence, and sexual
      When the system prompt composer builds the final instruction text
      Then an explicit content restriction hard override block is appended at the very end
      And the override declares non-negotiable prohibitions that supersede all aesthetic goals

  Rule: Passage writer jobs package timing, shots, tags, and domain enrichments

    @WRITER-04
    Scenario: Segment writer job structure formats shots, camera directions, and word count targets
      Given a planned segment containing 3 shots with musical cut timestamps
      When the pipeline constructs the writer request job
      Then the job payload specifies segment_id, duration_seconds, and shot_count
      And each shot specifies duration, scale, camera motion, energy, and sampled vocabulary
      And length_requirement defines a scaled word window based on shot count

    @WRITER-05
    Scenario Outline: Domain enrichments inject choreography, lip sync, and instruments into writer job
      Given a passage configured for "<capability>"
      When the job payload is constructed
      Then the request object includes the "<enrichment_key>" payload
      And the corresponding domain rules are appended to the system instructions

      Examples:
        | capability             | enrichment_key          |
        | lip_sync singing       | singing                 |
        | dance choreography     | dance                   |
        | instrument performance | instrument_performance  |
        | storyboard context     | storyboard              |

  Rule: Batch writer calls execute through local or API profiles with strict timeouts

    @WRITER-06
    Scenario: LLM invocation delivers structured system and user prompts with usage observation
      Given an assembled writer job and system prompt
      When the engine executes call_llm against the writer endpoint
      Then the HTTP request transmits system and user messages with temperature 0.7
      And the writer usage observer monitors context window consumption and token throughput
      And the response content is received without stream buffering

