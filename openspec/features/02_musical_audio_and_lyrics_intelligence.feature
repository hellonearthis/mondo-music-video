@ai @audio @lyrics @stems
Feature: Musical Audio and Lyrics Intelligence
  As a music video planner
  I want speech recognition and source separation to analyze song timing, lyrics, and stem parts
  So that visual pacing, actor dance choreography, and performer singing match the acoustic rhythm

  Background:
    Given a valid audio track is uploaded to the studio
    And the audio meter and beat division are declared

  Rule: Whisper speech models detect lyric words and time pasted lines

    @AUDIO-01
    Scenario Outline: Automatic speech recognition detects timed lyrics with selectable accuracy
      Given the Whisper speech model "<model_tier>" is present in local storage
      When the lyrics detection worker listens to the song audio
      Then the system produces timed lyric segments on the song timeline
      And the word intervals are categorized with matched or estimated timing confidence

      Examples:
        | model_tier |
        | tiny       |
        | base       |
        | small      |
        | medium     |
        | large-v3   |

    @AUDIO-02
    Scenario: Alignment of pasted lyric lines against speech detection timestamps
      Given a song that has been previously transcribed by lyrics detection
      And a multiline string of authored lyric text
      When the lyric alignment worker correlates the lines with detected acoustic tokens
      Then each lyric line is mapped to a start second and end second on the song clock
      And lines with ambiguous phonetic matches receive an uncertain timing flag

  Rule: Musical stem separation drives per-part energy and choreography

    @AUDIO-03
    Scenario: Demucs model extraction isolates independent instrument and vocal stems
      Given stem separation is requested with stem quality standard or high
      When the stem separation worker runs Demucs across the mix
      Then six distinct audio stems are generated: drums, bass, vocals, guitar, piano, and other
      And each stem produces an independent energy profile synchronized to downbeat frames

    @AUDIO-04
    Scenario: Vocal acoustic analysis warns on cast gender dissonance without blocking
      Given a cached vocals stem is available for the musical track
      And the cast assigns an actor to the main singing role
      When the voice analysis check compares vocal formants to actor presentation
      Then the system generates an advisory note if vocal timbre contrasts with the singer
      And the quote preview continues without halting production

