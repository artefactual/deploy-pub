"""Decision points of the Archivematica workflow and the targets of their choices.

Generated from the MCPServer/assets/workflow.json of each supported Archivematica
line, 1.18 and qa/1.x, merged by tools/extract_decisions.py; regenerate it when
one of those workflows changes or the supported lines change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    link_id: str
    choices: dict[str, str]


DECISIONS: dict[str, tuple[Decision, ...]] = {
    "Approve AIC": (
        Decision(
            "6404ce13-8619-48ba-b12f-aa7a034153ac",
            {
                "Approve AIC": "5f34245e-5864-4199-aafc-bc0ada01d4cd",
                "Reject": "169a5448-c756-4705-a920-737de6b8d595",
            },
        ),
    ),
    "Approve AIP reingest": (
        Decision(
            "9520386f-bb6d-4fb9-a6b6-5845ef39375f",
            {
                "Approve AIP reingest": "260ef4ea-f87d-4acf-830d-d0de41e6d2af",
                "Reject SIP": "a6ed697e-6189-4b4e-9f80-29209abc7937",
            },
        ),
    ),
    "Approve DSpace transfer": (
        Decision(
            "b963a646-0569-43c4-89a2-e3b814c5c08e",
            {
                "Reject transfer": "1b04ec43-055c-43b7-9543-bd03c6a778ba",
                "Approve transfer": "1cb2ef0e-afe8-45b5-8d8f-a1e120f06605",
            },
        ),
    ),
    "Approve Dataverse transfer": (
        Decision(
            "246943e4-d203-48e1-ac84-4865520e7c30",
            {
                "Reject transfer": "1b04ec43-055c-43b7-9543-bd03c6a778ba",
                "Approve Dataverse transfer": "10c00bc8-8fc2-419f-b593-cf5518695186",
            },
        ),
    ),
    "Approve SIP Creation": (
        Decision(
            "ab69c494-23b7-4f50-acff-2e00cf7bffda",
            {
                "SIP Creation complete": "2eae85d6-da2f-4f1c-8c33-3810b55e23aa",
                "Reject SIP": "a6ed697e-6189-4b4e-9f80-29209abc7937",
            },
        ),
    ),
    "Approve TRIM transfer": (
        Decision(
            "8db10a7b-924f-4561-87b4-cb6078c65aab",
            {
                "Reject transfer": "1b04ec43-055c-43b7-9543-bd03c6a778ba",
                "Approve transfer": "e4a59e3e-3dba-4eb5-9cf1-c1fb3ae61fa9",
            },
        ),
    ),
    "Approve bagit transfer": (
        Decision(
            "f6bcc82a-d629-4a78-8643-bf6e3cb39fe6",
            {
                "Reject transfer": "1b04ec43-055c-43b7-9543-bd03c6a778ba",
                "Approve transfer": "c75ef451-2040-4511-95ac-3baa0f019b48",
            },
        ),
    ),
    "Approve maildir transfer": (
        Decision(
            "998044bb-6260-452f-a742-cfb19e80125b",
            {
                "Approve transfer": "d381cf76-9313-415f-98a1-55c91e4d78e0",
                "Reject transfer": "1b04ec43-055c-43b7-9543-bd03c6a778ba",
            },
        ),
    ),
    "Approve normalization": (
        Decision(
            "de909a42-c5b5-46e1-9985-c031b50e9d30",
            {
                "Yes": "1e0df175-d56d-450d-8bee-7df1dc7ae815",
                "Redo": "cbe9b4a3-e4e6-4a32-8d7c-3adfc409cb6f",
                "Reject": "169a5448-c756-4705-a920-737de6b8d595",
            },
        ),
    ),
    "Approve standard transfer": (
        Decision(
            "0c94e6b5-4714-4bec-82c8-e187e0c04d77",
            {
                "Approve transfer": "6953950b-c101-4f4c-a0c3-0cd0684afe5e",
                "Reject transfer": "1b04ec43-055c-43b7-9543-bd03c6a778ba",
            },
        ),
    ),
    "Approve zipped bagit transfer": (
        Decision(
            "15402367-2d3f-475e-b251-55532347a3c2",
            {
                "Approve transfer": "167dc382-4ab1-4051-8e22-e7f1c1bf3e6f",
                "Reject transfer": "1b04ec43-055c-43b7-9543-bd03c6a778ba",
            },
        ),
    ),
    "Approve zipped transfer": (
        Decision(
            "44e0b981-78d2-4403-8233-05038b3cc603",
            {
                "Approve transfer": "f3caceff-5ad5-4bad-b98c-e73f8cd03450",
                "Reject transfer": "1b04ec43-055c-43b7-9543-bd03c6a778ba",
            },
        ),
    ),
    "Assign UUIDs to directories?": (
        Decision(
            "1563f22f-f5f7-4dfe-a926-6ab50d408832",
            {
                "No": "dc0ee6b6-ed5f-42a3-bc8f-c9c7ead03ed1",
                "Yes": "efd98ddb-80a6-4206-80bf-81bf00f84416",
            },
        ),
        Decision(
            "8882bad4-561c-4126-89c9-f7f0c083d5d7",
            {
                "No": "0053c670-3e61-4a3e-a188-3a2dd1eda426",
                "Yes": "7e4cf404-e62d-4dc2-8d81-6141e390f66f",
            },
        ),
        Decision(
            "bd899573-694e-4d33-8c9b-df0af802437d",
            {
                "Yes": "2dc3f487-e4b0-4e07-a4b3-6216ed24ca14",
                "No": "891f60d0-1ba8-48d3-b39e-dd0934635d29",
            },
        ),
        Decision(
            "d6f6f5db-4cc2-4652-9283-9ec6a6d181e5",
            {
                "No": "6dfbeff8-c6b1-435b-833a-ed764229d413",
                "Yes": "aa793efa-1b62-498c-8f92-cab187a99a2a",
            },
        ),
        Decision(
            "e10a31c3-56df-4986-af7e-2794ddfe8686",
            {
                "Yes": "2732a043-b197-4cbc-81ab-4e2bee9b74d3",
                "No": "8e93e523-86bb-47e1-a03a-4b33e13f8c5e",
            },
        ),
    ),
    "Attempt restructure for compliance?": (
        Decision(
            "5c459c1a-f998-404d-a0dd-808709510b72",
            {
                "Attempt restructure for compliance": "082fa7d6-68e1-431c-9216-899aec92cfa7",
                "Reject transfer": "1b04ec43-055c-43b7-9543-bd03c6a778ba",
                "Move transfer back to activeTransfers directory": "191914db-119e-4b91-8422-c77805ad8249",
            },
        ),
    ),
    "Bind PIDs?": (
        Decision(
            "a2ba5278-459a-4638-92d9-38eb1588717d",
            {
                "Yes": "8f9dceb5-b978-43e0-a364-8b317a3ac43b",
                "No": "44a7c397-8187-4fd2-b8f7-c61737c4df49",
            },
        ),
    ),
    "Choose Config for ArchivesSpace DIP Upload": (
        Decision(
            "a0db8294-f02a-4f49-a557-b1310a715ffc",
            {},
        ),
    ),
    "Choose config for AtoM DIP upload": (
        Decision(
            "7f975ba6-2185-434c-b507-2911f3c77213",
            {},
        ),
    ),
    "Choose thumbnail mode": (
        Decision(
            "498f7a6d-1b8c-431a-aa5d-83f14f3c5e65",
            {
                "Yes": "c318b224-b718-4535-a911-494b1af6ff26",
                "Yes, without default icons": "89f098ef-1cb2-4a97-ad67-4c0f14d0546b",
                "No": "972fce6c-52c8-4c00-99b9-d6814e377974",
            },
        ),
    ),
    "Create SIP(s)": (
        Decision(
            "bb194013-597c-4e4a-8493-b36d190f8717",
            {
                "Create single SIP and continue processing": "61cfa825-120e-4b17-83e6-51a42b67d969",
                "Send to backlog": "7065d256-2f47-4b7d-baec-2c4699626121",
                "Reject transfer": "1b04ec43-055c-43b7-9543-bd03c6a778ba",
            },
        ),
    ),
    "Delete package after extraction?": (
        Decision(
            "f19926dd-8fb5-4c79-8ade-c83f61f55b40",
            {
                "Yes": "85b1e45d-8f98-4cae-8336-72f40e12cbef",
                "No": "72e8443e-a8eb-49a8-ba5f-76d52f960bde",
            },
        ),
    ),
    "Do you want to perform file format identification?": (
        Decision(
            "087d27be-c719-47d8-9bbb-9a7d8b609c44",
            {
                "Yes": "4dec164b-79b0-4459-8505-8095af9655b5",
                "No": "782bbf56-e220-48b5-9eb6-6610583f2072",
            },
        ),
        Decision(
            "7a024896-c4f7-4808-a240-44c87c762bc5",
            {
                "Yes": "5b3c8268-5b33-4b70-b1aa-0e4540fe03d1",
                "No, use existing data": "3c1faec7-7e1e-4cdd-b3bd-e2f05f4baa9b",
            },
        ),
        Decision(
            "f09847c2-ee51-429a-9478-a860477f6b8d",
            {
                "Yes": "d97297c7-2b49-4cfe-8c9f-0613d63ed763",
                "No": "1f77af0a-2f7a-468f-af8c-653a9e61ca4f",
            },
        ),
    ),
    "Do you want to scan for viruses in attachments?": (
        Decision(
            "390d6507-5029-4dae-bcd4-ce7178c9b560",
            {
                "Yes": "34944d4f-762e-4262-8c79-b9fd48521ca0",
                "No": "63be6081-bee8-4cf5-a453-91893e31940f",
            },
        ),
    ),
    "Do you want to scan for viruses in directories?": (
        Decision(
            "7e81f94e-6441-4430-a12d-76df09181b66",
            {
                "Yes": "97be337c-ff27-4869-bf63-ef1abc9df15d",
                "No": "77355172-b437-4324-9dcc-e2607ad27cb1",
            },
        ),
    ),
    "Do you want to scan for viruses in extracted files?": (
        Decision(
            "1dad74a2-95df-4825-bbba-dca8b91d2371",
            {
                "Yes": "1ac7d792-b63f-46e0-9945-d48d9e5c02c9",
                "No": "697c0883-798d-4af7-b8b6-101c7f709cd5",
            },
        ),
    ),
    "Do you want to scan for viruses in metadata?": (
        Decision(
            "856d2d65-cd25-49fa-8da9-cabb78292894",
            {
                "Yes": "6e431096-c403-4cbf-a59a-a26e86be54a8",
                "No": "63767e4b-9ce8-4fe2-8724-65cc1f763de0",
            },
        ),
    ),
    "Do you want to scan for viruses in submission documentation?": (
        Decision(
            "97a5ddc0-d4e0-43ac-a571-9722405a0a9b",
            {
                "Yes": "3e8c0c39-3f30-4c9b-a449-85eef1b2a458",
                "No": "7f5244fe-590b-4e38-beaf-0cf1ccb9e71b",
            },
        ),
    ),
    "Document empty directories?": (
        Decision(
            "d0dfa5fc-e3c2-4638-9eda-f96eea1070e0",
            {
                "Yes": "29881c21-3548-454a-9637-ebc5fd46aee0",
                "No": "65273f18-5b4e-4944-af4f-09be175a88e8",
            },
        ),
    ),
    "Examine contents?": (
        Decision(
            "accea2bf-ba74-4a3a-bb97-614775c74459",
            {
                "Examine contents": "06f03bb3-121d-4c85-bec7-abbc5320a409",
                "Skip examine contents": "e0a39199-c62a-4a2f-98de-e9d1116460a8",
            },
        ),
    ),
    "Extract packages?": (
        Decision(
            "dec97e3c-5598-4b99-b26e-f87a435a6b7f",
            {
                "Yes": "01d80b27-4ad1-4bd1-8f8d-f819f18bf685",
                "No": "79f1f5af-7694-48a4-b645-e42790bbf870",
            },
        ),
    ),
    "Generate transfer structure report": (
        Decision(
            "56eebd45-5600-4768-a8c2-ec0114555a3d",
            {
                "Yes": "df54fec1-dae1-4ea6-8d17-a839ee7ac4a7",
                "No": "e9eaef1e-c2e0-4e3b-b942-bfb537162795",
            },
        ),
    ),
    "Normalize": (
        Decision(
            "7509e7dc-1e1b-4dce-8d21-e130515fce73",
            {
                "Normalize for preservation": "612e3609-ce9a-4df6-a9a3-63d634d2d934",
                "Do not normalize": "e8544c5e-9cbb-4b8f-a68b-6d9b4d7f7362",
                "Reject SIP": "a6ed697e-6189-4b4e-9f80-29209abc7937",
            },
        ),
        Decision(
            "cb8e5706-e73f-472f-ad9b-d1236af8095f",
            {
                "Normalize for preservation and access": "b93cecd4-71f2-4e28-bc39-d32fd62c5a94",
                "Normalize for preservation": "612e3609-ce9a-4df6-a9a3-63d634d2d934",
                "Normalize for access": "fb7a326e-1e50-4b48-91b9-4917ff8d0ae8",
                "Normalize service files for access": "e600b56d-1a43-4031-9d7c-f64f123e5662",
                "Normalize manually": "c34bd22a-d077-4180-bf58-01db35bdb644",
                "Do not normalize": "89cb80dd-0636-464f-930d-57b61e3928b2",
                "Reject SIP": "a6ed697e-6189-4b4e-9f80-29209abc7937",
            },
        ),
    ),
    "Perform policy checks on access derivatives?": (
        Decision(
            "8ce07e94-6130-4987-96f0-2399ad45c5c2",
            {
                "Yes": "d9760427-b488-4381-832a-de10106de6fe",
                "No": "76befd52-14c3-44f9-838f-15a4e01624b0",
            },
        ),
    ),
    "Perform policy checks on originals?": (
        Decision(
            "70fc7040-d4fb-4d19-a0e6-792387ca1006",
            {
                "Yes": "c611a6ff-dfdb-46d1-b390-f366a6ea6f66",
                "No": "3e891cc4-39d2-4989-a001-5107a009a223",
            },
        ),
    ),
    "Perform policy checks on preservation derivatives?": (
        Decision(
            "153c5f41-3cfb-47ba-9150-2dd44ebc27df",
            {
                "Yes": "3a55f688-eca3-4ebc-a012-4ce68290e7b0",
                "No": "b7ce05f0-9d94-4b3e-86cc-d4b2c6dba546",
            },
        ),
    ),
    "Reminder: add metadata if desired": (
        Decision(
            "eeb23509-57e2-4529-8857-9d62525db048",
            {
                "Continue": "5727faac-88af-40e8-8c10-268644b0142d",
            },
        ),
    ),
    "Select compression algorithm": (
        Decision(
            "01d64f58-8295-4b7b-9cab-8f1b153a504f",
            {
                "7z using bzip2": "9475447c-9889-430c-9477-6287a9574c5b",
                "7z using lzma": "c96353b9-0d55-46cf-baa0-d7c3e180dd43",
                "7z without compression": "e3906da0-41fb-4cb8-a598-6c73981b63e9",
                "Gzipped tar": "9ce711ab-96d1-45dd-8708-de69698c1424",
                "Parallel bzip2": "f61b00a1-ef2e-4dc4-9391-111c6f42b9a7",
                "Uncompressed": "dc04c4c0-07ea-4796-b643-66d967ed33a4",
            },
        ),
    ),
    "Select compression level": (
        Decision(
            "01c651cb-c174-4ba4-b985-1d87a44d6754",
            {
                "1 - fastest compression": "ecfad581-b007-4612-a0e0-fcc551f4057f",
                "3 - fast compression": "85b2243e-ff97-4ca8-80e8-3c6b0842b360",
                "5 - normal compression": "414da421-b83f-4648-895f-a34840e3c3f5",
                "7 - maximum compression": "4e31f579-68bd-4be1-a10e-ec5411897121",
                "9 - ultra compression": "6d52fd24-8c06-4c8e-997a-e427ba0acc36",
            },
        ),
    ),
    "Store AIP": (
        Decision(
            "2d32235c-02d4-4686-88a6-96f4d6c7b1c3",
            {
                "Yes": "9efab23c-31dc-4cbd-a39d-bb1665460cbe",
                "Reject AIP": "433f4e6b-1ef4-49f8-b1e4-49693791a806",
            },
        ),
    ),
    "Store DIP?": (
        Decision(
            "5e58066d-e113-4383-b20b-f301ed4d751c",
            {
                "Store DIP": "8d29eb3d-a8a8-4347-806e-3d8227ed44a1",
                "Reject DIP": "4500f34e-f004-4ccf-8720-5c38d0be2254",
            },
        ),
    ),
    "Transcribe SIP contents?": (
        Decision(
            "82ee9ad2-2c74-4c7c-853e-e4eaf68fc8b6",
            {
                "Yes": "35151db8-3a11-4b49-8865-f6697ef0ac75",
                "No": "0a24787c-00e3-4710-b324-90e792bfb484",
            },
        ),
    ),
    "Upload DIP": (
        Decision(
            "92879a29-45bf-4f0b-ac43-e64474f0f2f9",
            {
                "Upload DIP to AtoM": "0fe9842f-9519-4067-a691-8a363132ae24",
                "Upload DIP to ArchivesSpace": "3572f844-5e69-4000-a24b-4e32d3487f82",
                "Upload DIP to CONTENTdm": "526eded3-2280-4f10-ac86-eff6c464cc81",
                "Do not upload DIP": "6eb8ebe7-fab3-4e4c-b9d7-14de17625baa",
            },
        ),
    ),
}
