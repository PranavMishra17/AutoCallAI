import { BaseConversation, type PartialOptions } from "./BaseConversation";
import { TextConversation } from "./TextConversation";
import { VoiceConversation } from "./VoiceConversation";
export type { Mode, Role, Options, PartialOptions, ClientToolsConfig, Callbacks, Status, AudioWorkletConfig, } from "./BaseConversation";
export type { InputConfig } from "./utils/input";
export type { OutputConfig } from "./utils/output";
export { Input } from "./utils/input";
export { Output } from "./utils/output";
export type { IncomingSocketEvent, VadScoreEvent, AudioAlignmentEvent, } from "./utils/events";
export type { SessionConfig, BaseSessionConfig, DisconnectionDetails, Language, ConnectionType, FormatConfig, } from "./utils/BaseConnection";
export { createConnection } from "./utils/ConnectionFactory";
export { WebSocketConnection } from "./utils/WebSocketConnection";
export { WebRTCConnection } from "./utils/WebRTCConnection";
export { postOverallFeedback } from "./utils/postOverallFeedback";
export { SessionConnectionError } from "./utils/errors";
export { VoiceConversation } from "./VoiceConversation";
export { TextConversation } from "./TextConversation";
export { Scribe, AudioFormat, CommitStrategy, RealtimeEvents, RealtimeConnection, } from "./scribe";
export type { AudioOptions, MicrophoneOptions, WebSocketMessage, PartialTranscriptMessage, CommittedTranscriptMessage, CommittedTranscriptWithTimestampsMessage, ScribeErrorMessage, ScribeAuthErrorMessage, ScribeQuotaExceededErrorMessage, ScribeCommitThrottledErrorMessage, ScribeTranscriberErrorMessage, ScribeUnacceptedTermsErrorMessage, ScribeRateLimitedErrorMessage, ScribeInputErrorMessage, ScribeQueueOverflowErrorMessage, ScribeResourceExhaustedErrorMessage, ScribeSessionTimeLimitExceededErrorMessage, ScribeChunkSizeExceededErrorMessage, ScribeInsufficientAudioActivityErrorMessage, } from "./scribe";
export declare class Conversation extends BaseConversation {
    static startSession(options: PartialOptions & {
        textOnly: true;
    }): Promise<TextConversation>;
    static startSession(options: PartialOptions & {
        textOnly: false;
    }): Promise<VoiceConversation>;
    static startSession(options: PartialOptions): Promise<TextConversation | VoiceConversation>;
}
