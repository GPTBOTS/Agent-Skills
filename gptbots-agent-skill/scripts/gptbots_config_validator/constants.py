from typing import Final

BOT_TYPES: Final = {"QuestionAnswer", "Flow", "Workflow"}
EXPORT_TYPES: Final = {"BOT", "WORKFLOW"}
MAX_FILE_SIZE: Final = 50 * 1024 * 1024

HUMAN_MANUFACTURERS: Final = {
    "Intercom",
    "Webhook",
    "LiveChat",
    "SoBot",
    "ZohoSalesIQ",
    "LiveDesk",
    "Omnichat",
}
HUMAN_CONFIG_STATUS: Final = {"enable", "disable"}
HUMAN_MESSAGE_CODES: Final = {29, 30, 31, 33, 34, 35, 36, 37, 38, 84}
CUSTOM_VARIABLE_TYPES: Final = {
    "STRING",
    "INTEGER",
    "NUMBER",
    "BOOLEAN",
    "DATETIME",
    "OBJECT",
    "ARRAY_STRING",
    "ARRAY_INTEGER",
    "ARRAY_NUMBER",
    "ARRAY_BOOLEAN",
    "ARRAY_OBJECT",
    "FILE",
    "ARRAY_FILE",
}
USER_PROPERTY_TYPES: Final = {"string", "number", "datetime", "bool", "list"}

FLOW_COMPONENT_TYPES: Final = {
    "Input",
    "Output",
    "LLM",
    "Bool",
    "Branch",
    "Predefine",
    "Dataset",
    "Human",
    "Condition",
    "Regular",
    "ChatGather",
    "FormGather",
    "Message",
    "ToolApi",
    "Workflow",
    "Variable",
}
WORKFLOW_NODE_TYPES: Final = {
    "START",
    "END",
    "LLM",
    "DATABASE",
    "DATASET",
    "AUDIO_LLM",
    "INTENT",
    "CODE",
    "HTTP",
    "CONDITION",
    "COMMENT",
    "TOOL_API",
    "FILE_PARSE",
    "TEXT_PROCESS",
    "VARIABLE_AGGREGATE",
    "LOOP",
    "BATCH",
    "NEXT_LOOP",
    "CONTINUE",
    "BREAK",
    "SET_INTERMEDIATE_VARIABLE",
}
NODE_REQUIRED_PARAM: Final = {
    "LLM": "llmParam",
    "AUDIO_LLM": "audioLlmParam",
    "CODE": "codeParam",
    "CONDITION": "conditionParam",
    "DATABASE": "databaseParam",
    "DATASET": "datasetParam",
    "HTTP": "httpParam",
    "INTENT": "intentParam",
    "COMMENT": "commentParam",
    "TOOL_API": "toolApiParam",
    "FILE_PARSE": "fileParseParam",
    "TEXT_PROCESS": "textProcessParam",
    "VARIABLE_AGGREGATE": "variableAggregateParam",
    "LOOP": "loopParam",
    "BATCH": "batchParam",
    "SET_INTERMEDIATE_VARIABLE": "setIntermediateVariableParam",
    "END": "endParam",
}

REASONING_EFFORTS: Final = {"MINIMAL", "LOW", "MEDIUM", "HIGH"}
REASONING_SHOW: Final = {"SHOW", "COLLAPSE", "HIDDEN"}
DATA_SOURCE_SHOW: Final = {"MIN_SHOW", "LIST_SHOW", "CORNER_SHOW"}
CUSTOM_KNOWLEDGE_TYPES: Final = {"DEFAULT", "LLM"}
RESPONSE_FORMATS: Final = {"Text", "JsonObject", "JsonSchema"}
MODE_TYPES: Final = {"general", "excellent", "specialist"}
MULTI_MODAL_DATA_TYPES: Final = {"Text", "Image", "File", "Audio", "Video", "Document"}
FLOW_CONTENT_TYPES: Final = {"Form", "Text", "Json", "Card"}
PROMPT_MESSAGE_TYPES: Final = {
    "Role",
    "LongMemory",
    "ShortMemory",
    "Dataset",
    "Input",
    "Output",
    "Plugin",
    "Content",
    "Choices",
    "Condition",
    "Attr",
    "Gather",
}
GATHER_FIELD_TYPES: Final = {"userProperty", "selfDefining"}
GATHER_VALUE_TYPES: Final = {"string", "bool", "integer", "number", "datetime", "list"}
OPTION_FIELD_TYPES: Final = {
    "string",
    "multiString",
    "bool",
    "integer",
    "number",
    "datetime",
    "phoneNumber",
    "email",
    "radio",
    "checkbox",
}
FORM_GATHER_TYPES: Final = {"single", "all"}
VARIABLE_TYPES: Final = {"USER_PROPERTY", "CUSTOM_VARIABLE"}
VARIABLE_OPERATE_TYPES: Final = {"CLEAR", "COVER", "APPEND"}
COMBINE_TYPES: Final = {"and", "or"}
REGULAR_CATEGORIES: Final = {
    "GlobalVariable",
    "UserProperty",
    "BrowserProperty",
    "Upstream",
    "WhatsApp",
    "Telegram",
    "LiveChat",
    "LiveDesk",
    "Line",
    "Start",
    "CustomVariable",
    "KeyEvent",
}
PROPERTY_TYPES: Final = {"string", "number", "datetime", "bool", "list"}
FILE_MODES: Final = {"SYSTEM", "LLM", "DISABLED"}

HANDLE_TARGET_KEY: Final = {
    "Input": "input",
    "Output": "output",
    "LLM": "LLM",
    "Bool": "boolean",
    "Branch": "branch",
    "Predefine": "preset",
    "Message": "message",
    "Dataset": "knowledge",
    "Human": "artificial",
    "Condition": "conditions",
    "Regular": "regular",
    "ChatGather": "qa-collect",
    "FormGather": "form-collect",
    "Workflow": "workflow",
    "ToolApi": "toolapi",
    "Variable": "variable",
}
HANDLE_SOURCE_KEY: Final = {
    key: value for key, value in HANDLE_TARGET_KEY.items() if key not in {"Output", "Human"}
}
HANDLE_SOURCE_KEY["FormGather"] = "formgather"
