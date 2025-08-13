import pytest

from test_utils.fixtures import Fixtures
from utils.sftp import insert_timestamp, assemble_object_key

dt = Fixtures.fixed_datetime()

class Test_Files_Module:

    @pytest.mark.unit
    def test_should_insert_UTC_timestamps(self):
        assert insert_timestamp(file_name='foo.zip', current_datetime=lambda: dt) == 'foo_(2023-10-13_13-21-33_UTC).zip'        
        assert insert_timestamp(file_name='foo', current_datetime=lambda: dt) == 'foo_(2023-10-13_13-21-33_UTC)'        
        assert insert_timestamp(file_name='folder/file.zip', current_datetime=lambda: dt) == 'folder/file_(2023-10-13_13-21-33_UTC).zip'        
        assert insert_timestamp(file_name='parent/child/file.name.zip', current_datetime=lambda: dt) == 'parent/child/file.name_(2023-10-13_13-21-33_UTC).zip'        

    @pytest.mark.unit
    def test_should_insert_SGT_timestamps(self):
        assert insert_timestamp(file_name='foo.zip', current_datetime=lambda: dt, use_sgt=True) == 'foo_(2023-10-13_21-21-33_SGT).zip'        
        assert insert_timestamp(file_name='folder/file.zip', current_datetime=lambda: dt, use_sgt=True) == 'folder/file_(2023-10-13_21-21-33_SGT).zip'   

    def test_should_assemble_proper_object_key(self):
        def obj_key(path: str, peer_id: str) -> str:
            return assemble_object_key(
                peer_id=peer_id,
                timestamp_tagging=False,
                current_datetime=lambda: dt,
                sftp_file_item=Fixtures.create_sftp_file_item(filename=path.split("/")[-1], location=path)
            )

        assert obj_key(path="test.txt", peer_id="abc") == "abc/test.txt"
        assert obj_key(path="/test.txt", peer_id="abc") == "abc/test.txt"
        assert obj_key(path="./test.txt", peer_id="abc") == "abc/test.txt"
        assert obj_key(path="//test.txt", peer_id="abc") == "abc/test.txt"
        assert obj_key(path="/./test.txt", peer_id="abc") == "abc/test.txt"
        assert obj_key(path="//tes/t.txt", peer_id="abc") == "abc/tes/t.txt"
        assert obj_key(path="////test.txt", peer_id="abc") == "abc/test.txt"
        assert obj_key(path="//_test.txt", peer_id="abc") == "abc/_test.txt"


