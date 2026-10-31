@ai @render @comfyui @gpu
Feature: ComfyUI Video Generation and Conditioning
  As the generative media backend
  I want to assemble node graphs with actor latents, audio timing, and render seeds
  So that validated text prompts are synthesized into high-definition video clips without VRAM deadlocks

  Background:
    Given all passage prompts for the production are validated and bound
    And ComfyUI is operational or configured for auto-launch

  Rule: GPU memory handoff frees resources before starting renderer

    @RENDER-01
    Scenario: Prompt writer and Laya decision model are unloaded to release VRAM
      Given the prompt synthesis stage has completed all passages
      When the worker prepares to invoke the ComfyUI video generator
      Then the Laya agent and tokenizer are deallocated and garbage collected
      And torch CUDA cache is cleared
      And the system waits until GPU memory usage returns to pre-writer levels

  Rule: Workflow builder injects actor portraits, audio conditioning, and render parameters

    @RENDER-02
    Scenario: Node graph injection wires actor references and audio downbeat latents
      Given a passage requiring 2 actor references and musical synchronization
      When WorkflowBuilder builds the execution graph from the template
      Then actor reference images are mapped into the reference image loader nodes
      And the musical audio slice is connected to the audio conditioning node
      And the render seed, aspect ratio, and step count are written into sampler inputs

    @RENDER-03
    Scenario Outline: Backend adapter routes generation to local or SDK proxy pipelines
      Given a production targeting renderer backend "<backend>"
      When the clip generation job is dispatched
      Then the pipeline executes "<adapter_behavior>"
      And progress is polled via the API until clip completion or timeout

      Examples:
        | backend      | adapter_behavior                                         |
        | local_h3     | direct HTTP POST to local ComfyUI instance on port 8188  |
        | comfy_sdk_h3 | authenticated Bearer token submission to Comfy proxy API |

