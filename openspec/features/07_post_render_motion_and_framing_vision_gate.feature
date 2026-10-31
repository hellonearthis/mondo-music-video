@ai @vision @quality @pixels
Feature: Post-Render Motion and Framing Vision Gate
  As an automated visual auditor
  I want frame sampling, pixel luminance differencing, border analysis, and vision AI inspection
  So that frozen clips, pillarboxed video, and visual artifacts are detected and rerolled automatically

  Background:
    Given a freshly rendered passage video clip from the renderer
    And the planned shot cut boundaries for the passage

  Rule: Deterministic frame sampling selects safe shot interiors excluding cuts

    @GATE-01
    Scenario: Frame sampler distributes inspection points across shot interiors
      Given a 120-frame passage containing internal cuts at frame 36 and frame 72
      When sample_frames selects an inspection budget of 8 frames
      Then cut guard frames within 2 frames of cut boundaries are strictly excluded
      And sample frames are placed across safe interiors and farthest midpoint gaps

  Rule: Algorithmic pixel gates detect frozen frames and letterbox borders

    @GATE-02
    Scenario: Luminance difference calculation identifies frozen motion failure
      Given a rendered clip that froze on a static frame during diffusion
      When frame_differences measures mean absolute luminance delta at 184x104 grayscale
      Then the calculated delta falls below the FROZEN_MOTION threshold of 0.35
      And the clip is classified as a motion failure

    @GATE-03
    Scenario: Edge standard deviation detects unwanted pillarbox or letterbox bars
      Given a rendered clip exhibiting uniform black bands along opposite margins
      When border analysis evaluates edge standard deviation against interior variance
      Then edge standard deviation falls below 2.0 while interior standard deviation exceeds 8.0
      And the clip is flagged for border framing defect

  Rule: Secondary vision AI inspects sampled frames for semantic defects

    @GATE-04
    Scenario: Vision model inspection classifies frame fill and visible defects
      Given vision quality checking is enabled in production settings
      When sampled frames are transmitted to the vision quality endpoint on port 8083
      Then the vision model returns a JSON evaluation of frame_fill and framing
      And any detected watermarks, projected film edges, or severe anatomical distortion are flagged

  Rule: Defective clips trigger automated local retries or operator alerts

    @GATE-05
    Scenario Outline: Quality gate responses differ by renderer cost policy
      Given a rendered clip fails the post-render motion or framing gate
      And the production is running on backend "<backend>"
      When the quality supervisor acts on the gate failure
      Then the system executes "<response_action>"
      And the judgment attempt is recorded in quality.json

      Examples:
        | backend   | response_action                                                     |
        | local_h3  | automatically reroll the clip with an offset seed up to retry limit |
        | wavespeed | record quality warning and alert operator without automatic spend   |

