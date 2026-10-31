@ai @vision @style
Feature: Style Harvesting via Vision AI
  As a music video director
  I want to harvest aesthetic directives and a style card from visual reference images
  So that generative video segments faithfully embody manufacturing and lighting traits without copying depiction content

  Background:
    Given the vision service endpoint is configured in settings
    And the vision model is staged and reachable at the configured URL

  Rule: The vision model extracts manufacturing decisions across eleven physical axes

    @HARVEST-01
    Scenario: Multi-reference visual harvest executes subtraction test and outputs style card
      Given 1 to 9 valid PNG reference images are staged in the uploads directory
      And the target style identifier does not collide with an existing style card
      When the vision style harvest pipeline processes the reference images
      Then the vision model receives a payload evaluating all eleven manufacturing axes
      And the prompt enforces the subtraction test to eliminate depictive subject nouns
      And the vision model returns a JSON object containing "style_card" and "aesthetic_directives"
      And the extracted style record is persisted to disk under the studio styles directory

    @HARVEST-02
    Scenario: Anti-pastiche constraint prevents artist and copyright names in aesthetic directives
      Given a set of reference images exhibiting recognizable artistic techniques
      When the vision harvester analyzes the images
      Then the prompt strictly instructs the model to describe traits instead of authorship
      And the directives omit named living artists, studios, and copyrighted works

  Rule: Harvest requests enforce strict input validation and boundary checks

    @HARVEST-03
    Scenario Outline: Invalid reference image inputs trigger immediate validation rejection
      Given a harvest request specifying "<condition>"
      When the pipeline prepares the harvest job
      Then the system raises a validation error stating "<expected_error>"
      And no HTTP completion request is dispatched to the vision service

      Examples:
        | condition                            | expected_error                              |
        | missing vision_model in settings     | Configure your vision model in Settings     |
        | empty reference image list           | Choose images to harvest                    |
        | non-png image extension              | Harvest reference image missing             |
        | path escaping the uploads directory  | is not in the uploads directory             |
        | existing style identifier            | That style already exists                   |

