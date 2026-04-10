import { BaseConversation, type PartialOptions } from "./BaseConversation";
export declare class TextConversation extends BaseConversation {
    readonly type = "text";
    static startSession(options: PartialOptions): Promise<TextConversation>;
}
