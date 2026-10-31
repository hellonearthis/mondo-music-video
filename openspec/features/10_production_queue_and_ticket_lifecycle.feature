@queue @tickets @lifecycle @safety @recovery
Feature: Production Queue and Atomic Ticket Lifecycle
  As a music video studio producer or automated agent
  I want a durable, sequential queue of whole productions with atomic ticket files and cost-hold invariants
  So that batch jobs run safely overnight without human intervention while strictly protecting against unauthorized API charges or duplicate rendering

  Background:
    Given the storage system initializes an atomic queue directory
    And the queue in-memory control state is initialized with running=false

  Rule: Free productions run without consent; paid productions require explicit fingerprint approval

    @QUEUE-01
    Scenario: Free local ticket is queued and dispatches automatically
      Given a previewed production request for local_h3 with zero estimated cost
      When the ticket is created in the queue
      Then its state is initialized to pending with estimate_usd 0 and no approved fingerprint
      And hold_reason evaluates to None
      And the queue dispatcher starts the production under the single-operation lock

    @QUEUE-02
    Scenario Outline: Paid ticket requires cost approval and is held if fingerprint or plan changes
      Given a paid production request estimated at "<estimate>" with approved fingerprint "<approved_fp>"
      When hold_reason is evaluated against current candidate fingerprint "<current_fp>"
      Then the ticket status is "<result_status>" with explanation "<explanation>"

      Examples:
        | estimate | approved_fp | current_fp | result_status | explanation                               |
        | 4.50     | fp-hash-a   | fp-hash-a  | runnable      | allowed to execute                        |
        | 4.50     | none        | fp-hash-a  | held          | never approved                            |
        | 4.50     | fp-hash-a   | fp-hash-b  | held          | inputs, settings or price changed         |

  Rule: Prior paid failures cascade holds onto subsequent paid tickets to prevent runaway spending

    @QUEUE-03
    Scenario: Earlier paid failure holds younger approved tickets until operator reviews
      Given an existing paid ticket that stopped in failed state at timestamp T1
      When a subsequent paid ticket approved before T1 is evaluated for dispatch
      Then hold_reason detects the earlier unrecovered paid stoppage
      And the ticket is held with "An earlier paid ticket did not finish"
      And no API tokens or GPU render credits are spent

  Rule: Queue order can be adjusted for waiting tickets while protecting active operations

    @QUEUE-04
    Scenario: Waiting tickets swap positions while running tickets reject mutation
      Given a queue containing two pending tickets at positions 1 and 2 and one running ticket
      When the operator moves the first pending ticket down by delta 1
      Then the two pending tickets swap their position values
      But attempting to move or delete the running ticket raises a validation error

  Rule: Process crashes cleanly interrupt active work and require explicit operator resume

    @QUEUE-05
    Scenario: Application restart marks running tickets interrupted and leaves queue paused
      Given a ticket was actively running when the application process terminated
      When the application recovers queue tickets on startup
      Then the ticket state transitions from running to interrupted
      And the queue running control flag remains false without automatic dispatch

    @QUEUE-06
    Scenario: Resuming an interrupted local ticket reuses completed prompts and finished clips
      Given an interrupted local ticket whose run directory contains completed prompts and Comfy receipts
      When the operator starts the queue or clicks resume on the ticket
      Then resume_ticket sets resume_run to the existing run ID and returns state to pending
      And the pipeline resumes inside the existing run folder without regenerating prompts or duplicating clips

  Rule: Operator cancellation halts the active job and pauses the entire queue

    @QUEUE-07
    Scenario: Cancelling a running production stops the ticket and pauses queue execution
      Given a queued production is actively executing under the single-operation lock
      When the operator dispatches a cancel command
      Then the active production transitions to cancelled
      And the queue control sets running=false to pause further dispatching
      And the remaining pending tickets stay untouched in the queue

