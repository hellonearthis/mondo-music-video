@ai @worlds @vocabulary @dissonance
Feature: Thematic Worlds and Vocabulary Dissonance
  As a visual director
  I want contextual vocabulary selection and Gaussian semantic dissonance
  So that visual settings, mechanisms, and lighting dynamically scale with musical intensity while maintaining stylistic cohesion

  Background:
    Given a suite of curated Thematic Worlds with signature vocabulary pools
    And a planned shot sequence with musical section energy values

  Rule: Effective dissonance scales vocabulary access based on audio energy and slider calibration

    @WORLDS-01
    Scenario: Low energy musical passages restrict vocabulary to tight focused slices
      Given an audio passage with energy below 0.35
      When energy-scaled vocabulary selection evaluates the segment
      Then shot vocabulary draws exclusively from the top 20% ranked terms of the active world
      And setting and subject types remain tightly clustered

    @WORLDS-02
    Scenario: High energy musical peaks unlock full table depth and stack secondary mechanisms
      Given an audio passage with energy exceeding 0.80
      When energy-scaled vocabulary selection processes the shots
      Then the full vocabulary table depth is accessible to the sampler
      And stackable slots combine primary and secondary mechanisms separated by commas

  Rule: Gaussian dissonance models semantic collision across world clusters

    @WORLDS-03
    Scenario Outline: Dimensional binding maps dissonance tiers to specific visual slots
      Given the Thematic Worlds mode is set to "<mode>"
      And the user dissonance slider is calibrated to <slider_value> percent
      When Gaussian dissonance calculates effective kappa for a shot
      Then the dimensional binding assigns visual slots to "<target_tier>" semantic clusters
      And Montage Grammar invariants preserve steady settings across Standard passages

      Examples:
        | mode   | slider_value | target_tier |
        | guided | 20           | base        |
        | guided | 55           | adjacent    |
        | strict | 75           | tension     |
        | strict | 90           | opposite    |
        | strict | 100          | maximal     |

  Rule: Musical downbeats and passage peaks trigger contrast world departures

    @WORLDS-04
    Scenario: Energetic shots borrow vocabulary from configured contrast worlds
      Given a production configuring world contrast roles for mirror, opposite, or tangent
      And a segment with energy exceeding the departure threshold
      When the world departure planner evaluates the shot
      Then terms from the departure world replace non-anchored shot slots
      And any established thematic mechanism anchor remains protected from replacement

    @WORLDS-05
    Scenario: Pre-compiled Thematic World centroids and distance matrix accelerate Gaussian dissonance
      Given the 10 built-in Thematic Worlds catalog in world_vectors
      When plan_gaussian_world_dissonance computes cluster weights without custom world_pools
      Then the planner reuses BUILTIN_WORLD_CENTROIDS and BUILTIN_CALIBRATED_MATRIX
      And avoids recomputing lexical embeddings or P15/P85 percentile bounds per call


