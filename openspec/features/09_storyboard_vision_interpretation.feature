@ai @storyboard @vision @alignment
Feature: Storyboard Vision Interpretation and Alignment
  As a visual storyteller
  I want storyboard image interpretation and proportional shot alignment
  So that hand-drawn or conceptual panels guide the video narrative without altering musical rhythm

  Background:
    Given up to 24 PNG storyboard panels uploaded to the studio
    And an active musical shot plan with established frame timing

  Rule: Vision AI interprets key narrative and visual directions from panel drawings

    @STORYBOARD-01
    Scenario: Vision model extracts panel directions without modifying musical structure
      Given a storyboard configured with narrative mode
      When the vision service interprets the uploaded panel images
      Then the model produces a concise prose direction for each panel
      And the panel directions describe framing, character action, and visual cues
      And the output JSON populates the storyboard panels list

  Rule: Mathematical timeline alignment maps panels to planned shots

    @STORYBOARD-02
    Scenario: Storyboard panels are proportionally distributed across planned shots
      Given a planned music video with 12 shots across 4 segments
      And a storyboard containing 6 interpreted panels
      When storyboard.align processes the plan
      Then each shot is mapped to a panel index based on chronological timeline position
      And shots within the same passage receive the corresponding panel directions
      And existing cut timestamps and musical frames remain strictly unmodified

    @STORYBOARD-03
    Scenario: Prompt writer jobs incorporate aligned storyboard context
      Given an aligned storyboard attached to the production request
      When the worker builds the writer job for a segment
      Then the job payload includes a storyboard object with shot-by-shot panel directions
      And the LLM writer prompt reflects the panel descriptions in its shot bodies

