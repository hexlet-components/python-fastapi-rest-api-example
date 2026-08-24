import "@typespec/http";
import "@typespec/rest";
import "@typespec/versioning";
import "@typespec/openapi3";
import "@typespec/openapi";

using TypeSpec.Versioning;
using TypeSpec.Http;
using TypeSpec.OpenAPI;

@service(#{ title: "Rest API Example" })
@info(#{
  license: #{
    name: "AGPL-3.0",
    url: "https://www.gnu.org/licenses/agpl-3.0.html",
  },
})
@server("http://localhost:8000", "Локальная разработка")
@versioned(Versions)
namespace PythonFastapiRestApiExample;

enum Versions {
  v1,
  v2,
}

/**
 * Идентификатор записи. Верхняя граница — не украшение схемы: без неё
 * значение проходит проверку, доезжает до базы и падает там на
 * переполнении, то есть 500 наступает на корректном с виду запросе.
 */
@minValue(1)
@maxValue(2147483647)
scalar ResourceId extends int32;

/**
 * https://www.rfc-editor.org/rfc/rfc9457.html
 */
@error
model ProblemDetails {
  @header("content-type") contentType: "application/problem+json";
  type?: string;
  title?: string;
  status?: integer;
  detail?: string;
  instance?: string;
}

@error
model BadRequestError {
  @statusCode _: 400;
  ...ProblemDetails;
}

@error
model UnprocessableEntityError {
  @statusCode _: 422;
  ...ProblemDetails;
  errors: Array<{
    message: string;
    rule: string;
    field: string;
  }>;
}

@error
model TooManyRequestsError {
  @statusCode _: 429;
  ...ProblemDetails;
}

// Эти три исхода возможны в любой операции: 400 отдаёт разбор тела, 422 —
// проверка по схеме и правила предметной области, 429 — ограничитель
// частоты. Исход, которого нет в контракте, клиент предусмотреть не может.
alias CommonErrors = BadRequestError | UnprocessableEntityError | TooManyRequestsError;

@error
model NotFoundError {
  @statusCode _: 404;
  ...ProblemDetails;
}

@error
model UnauthorizedError {
  @statusCode _: 401;
  ...ProblemDetails;
}

@error
model ForbiddenError {
  @statusCode _: 403;
  ...ProblemDetails;
}

@error
model ConflictError {
  @statusCode _: 409;
  ...ProblemDetails;
}

@error
model PreconditionFailedError {
  @statusCode _: 412;
  ...ProblemDetails;
}

/**
 * Где клиент находится и сколько всего есть. Без этого блока номер
 * страницы уходит в запрос, а обратно не возвращается ничего: узнать,
 * есть ли следующая страница, нельзя.
 */
model PageMeta {
  page: int32;
  perPage: int32;
  total: int32;
  totalPages: int32;
}

model User {
  id: int32;

  @minLength(2)
  @maxLength(100)
  fullName: string | null;

  // Nullable, а не необязательное: колонка добавляется существующей
  // таблице, и NOT NULL упёрся бы в уже лежащие строки.
  @added(Versions.v2) phone: string | null;

  @format("email")
  email: string;
}

model UserPage {
  data: User[];
  meta: PageMeta;
}

model UserCreateDTO {
  // Границы те же, что у User: иначе запрос принимает имя, которое
  // схема ответа потом забракует, и создание падает в 500.
  @minLength(2)
  @maxLength(100)
  fullName?: string | null;

  @format("email")
  email: string;

  @minLength(8)
  @secret
  password: string;

  @added(Versions.v2)
  @maxLength(30)
  phone?: string | null;
}

model UserEditDTO {
  // Имя объявлено вместе с null, а пароль — нет: колонка имени
  // nullable, поэтому null значит «стереть имя». Колонка пароля
  // объявлена NOT NULL, и пустоту в неё записать нельзя.
  @minLength(2)
  @maxLength(100)
  fullName?: string | null;

  @minLength(8)
  @secret
  password?: string;

  @added(Versions.v2)
  @maxLength(30)
  phone?: string | null;
}

model Course {
  id: int32;
  name: string;
  description: string;
}

model CoursePage {
  data: Course[];
  meta: PageMeta;
}

model CourseCreateDTO {
  @minLength(1)
  @maxLength(200)
  name: string;

  @minLength(1)
  description: string;
}

model CourseEditDTO {
  @minLength(1)
  @maxLength(200)
  name?: string;

  @minLength(1)
  description?: string;
}

model CourseLesson {
  id: int32;
  courseId: int32;
  name: string;
  body: string;
}

model CourseLessonPage {
  data: CourseLesson[];
  meta: PageMeta;
}

model CourseLessonCreateDTO {
  @minLength(1)
  @maxLength(200)
  name: string;

  @minLength(1)
  body: string;
}

model CourseLessonEditDTO {
  @minLength(1)
  @maxLength(200)
  name?: string;

  @minLength(1)
  body?: string;
}

model AuthInfo {
  @format("email")
  email: string;

  @secret
  password: string;
}

model TokenInfo {
  token: string;
}

alias Page = {
  @query @minValue(1) @maxValue(2147483647) page?: int32 = 1,

  // Потолок обязателен: без него запрос с perPage=1000000 заставляет
  // базу собрать всю таблицу в один ответ.
  @query @minValue(1) @maxValue(100) perPage?: int32 = 10,
};

/**
 * Метка версии из предыдущего чтения. Необязательна; если прислана и
 * запись с тех пор изменилась, правка отклоняется.
 */
alias IfMatch = {
  @header("If-Match") ifMatch?: string,
};

@route("/users")
namespace users {
  @summary("Список пользователей")
  @operationId("usersIndex")
  @get
  @useAuth(BearerAuth)
  op index(...Page): {
    @body users: UserPage;
  } | UnauthorizedError | CommonErrors;

  @summary("Пользователь по идентификатору")
  @operationId("usersShow")
  @get
  @useAuth(BearerAuth)
  op show(@path user_id: ResourceId): {
    @body user: User;
  } | NotFoundError | UnauthorizedError | CommonErrors;

  @summary("Регистрация пользователя")
  @operationId("usersCreate")
  @post
  op create(@body user: UserCreateDTO): {
    @statusCode statusCode: 201;
    @body user: User;
  } | CommonErrors;

  @summary("Изменение пользователя")
  @operationId("usersUpdate")
  @put
  @useAuth(BearerAuth)
  op update(@path user_id: ResourceId, @body user: UserEditDTO): {
    @body user: User;
  } | NotFoundError | UnauthorizedError | CommonErrors;

  @summary("Удаление пользователя")
  @operationId("usersDestroy")
  @delete
  @useAuth(BearerAuth)
  op destroy(@path user_id: ResourceId): {
    @statusCode statusCode: 204;
  } | NotFoundError | UnauthorizedError | ConflictError | CommonErrors;
}

@route("/tokens")
namespace tokens {
  @summary("Выдача токена по адресу и паролю")
  @operationId("tokensCreate")
  @post
  op create(@body authInfo: AuthInfo): {
    @statusCode statusCode: 201;
    @body token: TokenInfo;
  } | UnauthorizedError | CommonErrors;
}

@route("/courses")
namespace courses {
  @summary("Список курсов")
  @operationId("coursesIndex")
  @get
  op index(...Page): {
    @body courses: CoursePage;
  } | CommonErrors;

  @summary("Курс по идентификатору")
  @operationId("coursesShow")
  @get
  op show(@path course_id: ResourceId): {
    @body course: Course;
  } | NotFoundError | CommonErrors;

  @summary("Создание курса")
  @operationId("coursesCreate")
  @post
  @useAuth(BearerAuth)
  op create(@body course: CourseCreateDTO): {
    @statusCode statusCode: 201;
    @body course: Course;
  } | UnauthorizedError | CommonErrors;

  @summary("Изменение курса")
  @operationId("coursesUpdate")
  @put
  @useAuth(BearerAuth)
  op update(@path course_id: ResourceId, @body course: CourseEditDTO, ...IfMatch):
    | {
        @body course: Course;
      }
    | NotFoundError
    | UnauthorizedError
    | ForbiddenError
    | PreconditionFailedError
    | CommonErrors;

  @summary("Удаление курса")
  @operationId("coursesDestroy")
  @delete
  @useAuth(BearerAuth)
  op destroy(@path course_id: ResourceId, ...IfMatch):
    | {
        @statusCode statusCode: 204;
      }
    | NotFoundError
    | UnauthorizedError
    | ForbiddenError
    | PreconditionFailedError
    | CommonErrors;
}

@route("/courses/{course_id}/lessons")
namespace courses_lessons {
  @summary("Список уроков курса")
  @operationId("coursesLessonsIndex")
  @get
  op index(@path course_id: ResourceId, ...Page): {
    @body lessons: CourseLessonPage;
  } | CommonErrors;

  @summary("Урок курса")
  @operationId("coursesLessonsShow")
  @get
  op show(@path course_id: ResourceId, @path lesson_id: ResourceId): {
    @body lesson: CourseLesson;
  } | NotFoundError | CommonErrors;

  @summary("Добавление урока в курс")
  @operationId("coursesLessonsCreate")
  @post
  @useAuth(BearerAuth)
  op create(@path course_id: ResourceId, @body lesson: CourseLessonCreateDTO): {
    @statusCode statusCode: 201;
    @body lesson: CourseLesson;
  } | NotFoundError | UnauthorizedError | ForbiddenError | CommonErrors;

  @summary("Изменение урока")
  @operationId("coursesLessonsUpdate")
  @put
  @useAuth(BearerAuth)
  op update(
    @path course_id: ResourceId,
    @path lesson_id: ResourceId,
    @body lesson: CourseLessonEditDTO,
  ): {
    @body lesson: CourseLesson;
  } | NotFoundError | UnauthorizedError | ForbiddenError | CommonErrors;

  @summary("Удаление урока")
  @operationId("coursesLessonsDestroy")
  @delete
  @useAuth(BearerAuth)
  op destroy(@path course_id: ResourceId, @path lesson_id: ResourceId): {
    @statusCode statusCode: 204;
  } | NotFoundError | UnauthorizedError | ForbiddenError | CommonErrors;
}
