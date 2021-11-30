# Snowflake Comments → Tableau Catalog Descriptions

Note: This method employs REST API commands in Python. While REST API commands are a functionality supported by Tableau, note that the use of python or other 3rd party applications and functions may not be supported by Tableau.

I did not have Oauth set up for my snowflake instance, but the code to get an access token is pretty simple once you have it set up. I’ve linked to alternative authentication methods below. 

Also, I am not a professional developer so take all this code with a grain of salt. *It’s probably far from optimized!*


WHY: When evaluating Tableau Catalog, many customers have asked how they can move field descriptions freely through their database to Tableau and have that populate downstream. This is extremely important for security and governance. 

Right now, a description can exist in Snowflake (known as a comment). However when an end user connects to that table in Tableau, the descriptions do not carry over. the Tableau user must manually add them through the server UI at the table level or each time at the datasource level in Tableau Desktop. This can lead to error, duplicative work, not to mention a lack of single source of truth due to lag time for updating the descriptions. 

This code seeks to improve the process by using python to automate the movement of Snowflake comments to field descriptions in Tableau Catalog. The script can be run at whatever cadence makes sense for your business.


BASIC WORKFLOW: 

By querying Snowflake by using the python connector, you can grab a table of metadata (including the comments) and store it in a pandas dataframe.

By querying the metadata API for a list of tables connected to data sources in Tableau, you can get a list of tables names and table LUIDs.
Note: you **cannot** get table LUID from MDAPI by querying tables object alone, but you can get published data source LUID and database LUID. You can get table LUID if you query database and query downstream tables OR by using the databaseTables object.


Then, using Tableau Metadata Methods REST API, you can easily publish descriptions to columns in a table. These cascade down to all published datasources using these columns. 

[Technical requirements](https://salesforce.quip.com/JylsAIZp3lgV#temp:C:IEJdf9a9fb357bd4b6d9a755d9c4)
[authenticate_snowflake](https://salesforce.quip.com/JylsAIZp3lgV#temp:C:IEJ1540c01a89804aa4875b3f3ec)
[authenticate_tableau](https://salesforce.quip.com/JylsAIZp3lgV#temp:C:IEJ0f41dbdca55f4cf5948217f81)
[get_table_luids](https://salesforce.quip.com/JylsAIZp3lgV#temp:C:IEJe40f69a6dd984c8593a285900)
[get_table_id](https://salesforce.quip.com/JylsAIZp3lgV#temp:C:IEJ313eb142404a47cabd104c69c)
[get_snow_descriptions](https://salesforce.quip.com/JylsAIZp3lgV#temp:C:IEJ90a526109eca4e319149eaa82)
[get_list_of_columns](https://salesforce.quip.com/JylsAIZp3lgV#temp:C:IEJ2b4caac8b5ff4bf3944134745)
[add_comments_to_tab_table](https://salesforce.quip.com/JylsAIZp3lgV#temp:C:IEJ64aa94da3625439ba9c4f6b17)
[publish_description_to_column](https://salesforce.quip.com/JylsAIZp3lgV#temp:C:IEJ19d3ecf1ec8d46fcbf268334c)
[update_table_descriptions](https://salesforce.quip.com/JylsAIZp3lgV#temp:C:IEJ769c93f0f4ad4ae2944ae01a0)

### Technical requirements

1. Python
2. Tableau Data Management Add-on
    1. While you can use the Metadata API for free, in order to publish descriptions through Metadata Methods REST API, you will need to have a license for the Data Management Add-on
3. Snowflake Account



Required packages
requests
json
snowflake.connector
pandas


First, Authenticate to Snowflake.
* * *

### authenticate_snowflake

for username/pw, read here: https://docs.snowflake.com/en/user-guide/python-connector-example.html#connecting-using-the-default-authenticator

for oauth and other types of authentication, read here: https://docs.snowflake.com/en/user-guide/python-connector-example.html#connecting-with-oauth

**Input**
username
password
account name
database name

**Output**
cursor object


```
def authenticate_snowflake(snow_u,snow_p,account_name,database_name):
    ctx = snowflake.connector.connect(
        user=snow_u,
        password=snow_p,
        account=account_name,
        database=database_name
        )
    cs = ctx.cursor()
    return(cs)
```

* * *
Then, Authenticate to Tableau to get temp token. This expires after some time. 
* * *

### authenticate_tableau

Using a PAT
https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_concepts_auth.htm#make-a-sign-in-request-with-a-personal-access-token

Note that you will replace your url. You could make it modular or just omit url_name and site_id if you only plan on updating 1 server, or your online instance. 

**Input**
url_name
PAT
token_name
site name

**Output**
string of temp token


```
def authenticate_tableau(url_name,PAT,site_name, token_name):
    url = "https://" + url_name + " /api/3.13/auth/signin"

    payload = json.dumps({
      "credentials": {
        "personalAccessTokenName": token_name,
        "personalAccessTokenSecret": PAT,
        "site": {
          "contentUrl": site_name
        }
      }
    })
    headers = {
      'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    response = response.text
    token_string = response.split('token="',2)
    token_string_split1 = token_string[1].split('"',1)
    token = token_string_split1[0]
    
    site_id = token_string[2].split('site id="',1)
    site_id = site_id.split('"')
    site_id = site_id[0]
    
    req_strings=[token,site_id]
    return(req_strings)
    return(token)
```

* * *
We can grab a list of snowflake tables that are used in datasources in Tableau by querying the Metadata API. This is different than querying the server using REST commands as it uses an entirely different API and QL (uses GraphQL). 

Note: In the Metadata API, since data is indexed separately from Postgres (which is what the REST API queries), the table ID is not going to be the same as the LUID. The LUID is the same one that the REST API uses, so make sure to grab that field and not the Metadata Table ID. Confused? Me too! Check out the docs [here](https://help.tableau.com/current/api/metadata_api/en-us/reference/table.doc.html) where it says 


[Image: Screen Shot 2021-11-22 at 1.27.06 PM.png]You could either loop through this function for each db name in snowflake OR you could remove the filter object on the mdapi_query to store that info in the pandas dataframe. For this use case, I simplified to automating descriptions for 1 database at a time.
* * *

### get_table_luids

**Input**
token
database_name
site
 url_name 

**Output**
pandas dataframe with TABLE_NAME and TABLE_LUID


```
def get_table_luids(url_name, database_name, token)
mdapi_query = '''
query get_databases {
  databases (filter: {connectionType: "snowflake", name:"''' + database_name + '''"}){
 name
 id
 tables{
     name
     id
     luid
 
 }

 
}
}
'''
auth_headers = auth_headers = {'accept': 'application/json','content-type': 'application/json','x-tableau-auth': token}
metadata_query = requests.post('https://'+ts_url + '/api/metadata/graphql', headers = auth_headers, verify=True, json = {"query": mdapi_query})
mdapi_result = json.loads(metadata_query.text)

k=0
table_luid_list = []
while k < len(mdapi_result['data']['databases'][0]['tables']):
    print(mdapi_result['data']['databases'][0]['tables'][k]['luid'])
    table_luid_list.append(mdapi_result['data']['databases'][0]['tables'][k]['luid'])
    k = k+1
    
table_dictionary = {"table_name":table_name_list, "table_luid":table_luid_list}
tableau_tables_info = pd.DataFrame(table_dictionary, columns=['table_name','table_luid'])

return(tableau_tables_info)
```

* * *
ALTERNATE FUNCTION: Using only the REST API, grab the table ID by matching the name of the table in Snowflake to the name of the table in Tableau. Of course, this requires that there is only 1 table with that name.
* * *

### get_table_id

https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_ref_metadata.htm#query_tables

```
GET api/*api-version*/sites/*site-id*/tables
```


**Input**
url_name
table_name
site_id
token

**Output**
string of table ID


```
def get_table_id(url_name, table_name, site_id, token):
    get_tables_url = "https://"+url_name+"/api/3.13/sites/"+site_id+"/tables"

    payload = ""
    headers = {
      'X-Tableau-Auth': token
    }

    table_response = requests.request("GET", get_tables_url, headers=headers, data=payload)
    table_id_string = table_response.text.split('name="'+table_name+'"',1)
    table_id_string_split1 = table_id_string[0].split('<table id="')
    table_id_string_split2 = table_id_string_split1[-1]
    table_id_string_split3 = table_id_string_split2[0:-1]
    table_id_string_split4 = table_id_string_split2[0:-2]
    return(table_id_string_split4)
```

* * *
Now that we have the table IDs and Names, we can get comments from snowflake and put them into a dataframe. 
* * *

### get_snow_descriptions

using Kevin Campbell’s example query
https://community.snowflake.com/s/question/0D50Z00009Iba87SAB/how-can-i-get-the-comments-associated-with-my-table-column-using-the-getddl-statement

This assumes you have put the database in the authenticate_snowflake function. if you wanted to have the database be dynamic, add it as a parameter to the function and add the command cs.execute(“USE DATABASE <database name>”)
(see here: https://docs.snowflake.com/en/sql-reference/sql/use-database.html#use-database)

```
def get_snow_descriptions(cursor_object, table_name):
    desc_table_pandas = cursor_object.execute("select column_name, comment from information_schema.columns where table_name = '"+table_name+"';").fetch_pandas_all()
    return(desc_table_pandas)
```

**Input**
table_name
cursor object (from auth function)

**Output**
pandas dataframe with COLUMN_NAME (str), COMMENT (str)

* * *
Then, grab all columns IDs in each Tableau Table. We will need column IDs to send the right REST commands.
* * *

### get_list_of_columns

https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_ref_metadata.htm#query_columns

```
GET api/*api-version*/sites/*site-id*/tables/*table-id*/columns
```

**Input**
url_name
table_id
site_id
token

**Output**
pandas dataframe with column name, column ID


```
def get_list_of_columns(url_name,table_id,site_id,token):
    get_columns_url = "https://"+url_name+"/api/3.13/sites/"+site_id"/tables"+table_id+'/columns'

    payload = ""
    headers = {
      'X-Tableau-Auth': token
    }

    columns_response = requests.request("GET", get_columns_url, headers=headers, data=payload)
    columns_resonse_split = columns_response.text.split('" name="')

    i = 0
    column_names_list = []
    column_ids_list = []
    while i < len(table_columns_split):
        if i%2 == 0: 
            #even number, grab the column ID
            column_id = table_columns_split[i].split('column id="', 1)
            column_id = column_id[1][0:-2]
            column_ids_list.append(column_id)
        if i%2 == 1:
            #odd number, this is to grab the name
            column_name = table_columns_split[i].split('"',1)
            column_name = column_name[0]
            column_names_list.append(column_name)
        i = i+1
    
    column_dictionary = {"column_name":column_names_list, "column_id":column_ids_list}
    tableau_column_info = pd.DataFrame(column_dictionary, columns=['column_name','column_id'])
    return(tableau_column_info)
    
```

* * *
Merge the snowflake comments with the tableau columns/column ids.
It is important to left join tableau columns table and  snowflake table from a compute standpoint as the table in Tableau may have less fields than the snowflake table (able to hide columns or remove them upon publishing the datasource/table to Tableau Server).
* * *

### add_comments_to_tab_table

**Input**
tableau_columns
snow_columns

**Output**
pandas dataframe with column_id (str), column_name (str), comment (str)


```
`def add_comments_to_tab_table(tableau_columns, snow_columns):`
`join_result = tableau_columns.merge(snow_columns, how='inner',left_on="column_name",right_on='COLUMN_NAME')`

`return(join_result)`
```

* * *
Individual function to update description of one column
* * *

### publish_description_to_column

https://help.tableau.com/current/api/rest_api/en-us/REST/rest_api_ref_metadata.htm#update_column

```
PUT api/*api-version*/sites/*site-id*/tables/*table-id*/columns/*column-id*
```


**Input**

url_name
table_id (str)
column_id
description_text
token
**Output**
success string

```
def publish_description_to_column(url_name,site_id,table_id,column_id, description_text,token):
    column_description_url = "https://"+url_name+"/api/3.13/sites/"+site_id+"/tables/" + table_id + "/columns/" + column_id

    payload = "<tsRequest>\n  <column description=\"" + description_text +" \">\n  </column>\n</tsRequest>"
    headers = {
        'X-Tableau-Auth': token,
      'Content-Type': 'text/plain'
    }

    column_description_response = requests.request("PUT", column_description_url, headers=headers, data=payload)

    column_description_response_code = column_description_response.text
    return('Success')
```

* * *
Agg function to loop through pandas dataframe with tableau column name, id, and description and update descriptions for each row.
* * *

### update_table_descriptions

**Input**
tab_data_frame
table_id
token

**Output**
success string


```
def update_table_descriptions(tab_data_frame, table_id, token):
    for index, rows in tab_data_frame.itterows():
        publish_description_to_column(table_id,tab_data_frame['column_id'], tab_data_frame['COMMENT'],token)
    return('Success overall')
```


* * *
