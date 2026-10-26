import re

class Transform:
    @staticmethod
    def remove_tile(text:str) -> str:
        blacklist = ["SHOWTABLET", "SHOW TABLET", "SHOWTABLET THANG ĐIỂM", "SHOWPHOTO"]

        text = re.sub(
            pattern=".*(?=({}))".format("|".join(blacklist)), repl="", string=text
        )
        text = re.sub(
            pattern="({})".format("|".join(blacklist)), repl="", string=text
        )

        return text
    
    @staticmethod
    def remove_html(text:str) -> str:
        return re.sub(
            pattern='\<(?:\"[^\"]*\"[\'\"]*|\'[^\']*\'[\'\"]*|[^\'\">])+\>',
            repl="",
            string=text
        )

    @staticmethod
    def remove_quotes(text:str) -> str:
        return re.sub(
            pattern='[\"\']',
            repl="",
            string=text
        )

    @staticmethod
    def remove_newlines(text:str) -> str:
        return re.sub(
            pattern=r'\n',
            repl="",
            string=text
        )

    @staticmethod
    def remove_resource(text:str) -> str:
        m = re.search(pattern="{#resource:(.+)}", string=text)

        if m:
            if len(re.sub(pattern="{#resource:(.+)}", repl="", string=text)) == 0:
                text = re.sub(pattern="{#resource:|#}", repl="", string=text)
            else:
                text = re.sub(pattern="{#resource:(.+)}", repl="", string=text)

        return text

    def format_text(text:str) -> str:
        text = Transform.remove_tile(text)
        text = Transform.remove_html(text)
        text = Transform.remove_quotes(text)
        text = Transform.remove_newlines(text)
        text = Transform.remove_resource(text)

        return text